'''
Created on May 10, 2012

@author: nils
'''
import os
from datetime import datetime
import logging
import uuid as uuid_lib

from django.conf import settings
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from celery.result import AsyncResult
from celery import chain
from django_extensions.db.fields import UUIDField
import requests
from requests.exceptions import HTTPError

import core
from core.utils import delete_analysis_index, skip_if_test_run
import data_set_manager
from file_store.models import FileStoreItem
from file_store.tasks import FileImportTask
"""
TODO: Refactor import data_set_manager. Importing
data_set_manager.tasks.generate_auxiliary_file()
results in a circular import error (see comments on PR #1590)
"""


logger = logging.getLogger(__name__)


"""
General:
- xyz_term = accession number of an ontology term
- xyz_source = reference to the ontology where xyz_term originates (defined in
    the investigation)
"""


class NodeCollection(models.Model):
    """Base class for Investigation and Study
    """
    uuid = UUIDField(unique=True, auto=True)
    identifier = models.TextField(blank=True, null=True)
    title = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    submission_date = models.DateField(blank=True, null=True)
    release_date = models.DateField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        # change dates from empty string to None (to pass validation)
        if "submission_date" in kwargs:
            if kwargs["submission_date"] == "":
                kwargs["submission_date"] = None
            else:
                kwargs["submission_date"] = self.normalize_date(
                    kwargs["submission_date"]
                )

        if "release_date" in kwargs:
            if kwargs["release_date"] == "":
                kwargs["release_date"] = None
            else:
                kwargs["release_date"] = self.normalize_date(
                    kwargs["release_date"]
                )

        super(NodeCollection, self).__init__(*args, **kwargs)

    def __str__(self):
        return (
            str(self.identifier) +
            (
                ": " +
                str(self.title) if str(self.title) != "" else ""
            ) +
            ": " +
            str(self.id)
        )

    def normalize_date(self, dateString):
        """Normalizes date strings in dd/mm/yyyy format to yyyy-mm-dd.
        Returns normalized date string if in expected unnormalized format or
        unnormalized date string.
        """
        logger.info("Converting date " + str(dateString) + " ...")
        try:
            # try reformatting incorrect date format used by Nature Scientific
            # Data
            return str(
                datetime.strftime(
                    datetime.strptime(
                        dateString,
                        "%d/%m/%Y"
                    ),
                    "%Y-%m-%d"
                )
            )
        except ValueError:
            # ignore - date either in correct format or in format not supported
            # (will cause a validation error handled separately)
            logger.info("Failed to convert date " + str(dateString))
            return dateString


class Publication(models.Model):
    """Investigation or Study Publication (ISA-Tab Spec 4.1.2.2, 4.1.3.3)"""
    collection = models.ForeignKey(NodeCollection)
    title = models.TextField(blank=True, null=True)
    authors = models.TextField(blank=True, null=True)
    pubmed_id = models.TextField(blank=True, null=True)
    doi = models.TextField(blank=True, null=True)
    status = models.TextField(blank=True, null=True)
    # TODO: do we really want to store ontology information for this?
    status_accession = models.TextField(blank=True, null=True)
    status_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.authors) + ": " + str(self.title)


class Contact(models.Model):
    """Investigation or Study Contact (ISA-Tab Spec 4.1.2.3, 4.1.3.7)"""
    collection = models.ForeignKey(NodeCollection)
    last_name = models.TextField(blank=True, null=True)
    first_name = models.TextField(blank=True, null=True)
    middle_initials = models.TextField(blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.TextField(blank=True, null=True)
    fax = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    affiliation = models.TextField(blank=True, null=True)
    # TODO: split on semicolon
    roles = models.TextField(blank=True, null=True)
    # TODO: do we really want to store ontology information for this?
    roles_accession = models.TextField(blank=True, null=True)
    roles_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return (
            str(self.first_name) +
            " " +
            str(self.last_name) +
            " (" +
            str(self.email) +
            ")"
        )


class Investigation(NodeCollection):
    isarchive_file = UUIDField(blank=True, null=True, auto=False)
    pre_isarchive_file = UUIDField(blank=True, null=True, auto=False)

    """easily retrieves the proper NodeCollection fields"""

    def is_isa_tab_based(self):
        return bool(self.isarchive_file)

    def get_file_store_item(self):
        """Get an Investigation's corresponding FileStoreItem instance"""
        file_store_item_uuid = (
            self.isarchive_file if self.is_isa_tab_based()
            else self.pre_isarchive_file
        )
        try:
            return FileStoreItem.objects.get(uuid=file_store_item_uuid)
        except (FileStoreItem.DoesNotExist,
                FileStoreItem.MultipleObjectsReturned) as e:
            logger.error(
                "Couldn't fetch Investigation: %s's FileStoreItem from UUID: "
                "%s %s", self, file_store_item_uuid, e
            )

    def get_identifier(self):
        if (self.identifier is None) or (self.identifier.strip() == ""):
            # if there's no investigation identifier, then there's only 1 study
            study = self.study_set.all()[0]
            return study.identifier
        return self.identifier

    def get_title(self):
        if self.title == '' or self.title is None:
            study = self.study_set.all()[0]
            return study.title
        return self.title

    def get_description(self):
        if self.description is None or self.description == '':
            study = self.study_set.all()[0]
            return study.description
        return self.description

    def get_study(self):
        try:
            return Study.objects.get(investigation=self)
        except(Study.DoesNotExist, Study.MultipleObjectsReturned) as e:
            raise RuntimeError("Couldn't properly fetch Study: {}".format(e))

    def get_study_count(self):
        return self.study_set.count()

    def get_assay(self):
        try:
            return Assay.objects.get(study=self.get_study())
        except(Assay.DoesNotExist, Assay.MultipleObjectsReturned) as e:
            raise RuntimeError("Couldn't properly fetch Assay: {}".format(e))

    def get_assay_count(self):
        studies = self.study_set.all()
        assay_count = 0
        for study in studies:
            assay_count += study.assay_set.count()

        return assay_count

    def get_file_store_items(self, exclude_metadata_file=False,
                             local_only=False):
        """Returns a list of all data files associated with an Investigation
        :param exclude_metadata_file: <Boolean> Whether or not to exclude
        the metadata file used to create the Investigation from the resulting
        list
        :param local_only:  <Boolean> Whether or not to only include
        FileStoreItems that have been imported into Refinery
        """
        file_store_items = [
            node.file_item for node in Node.objects.filter(
                study=self.get_study(), file_item__isnull=False
            ).select_related('file_item')
        ]
        if not exclude_metadata_file:
            file_store_items.append(self.get_file_store_item())
        return (
            [f for f in file_store_items if f.datafile] if local_only
            else file_store_items
        )

    def get_datafile_names(self, local_only=False,
                           exclude_metadata_file=False):
        """
        Returns a list of all data file names associated with an
        Investigation

        :param exclude_metadata_file: <Boolean> Whether or not to exclude
        the metadata file used to crete the Investigation from the resulting
        list
        :param local_only:  <Boolean> Whether or not to only include data
        file names of FileStoreItems that have been imported into Refinery
        """
        file_store_items = self.get_file_store_items(
            local_only=local_only, exclude_metadata_file=exclude_metadata_file
        )
        return sorted(
            [os.path.basename(f.source) for f in file_store_items]
        )


@receiver(pre_delete, sender=Investigation)
def _investigation_delete(sender, instance, **kwargs):
    """
    Removes an Investigation's associated FileStoreItem upon deletion being
    triggered.
    Having these extra checks is favored within a signal so that this logic
    is picked up on bulk deletes as well.

    See: https://docs.djangoproject.com/en/1.8/topics/db/models/
    #overriding-model-methods
    """
    instance.get_file_store_item().delete()


class Ontology(models.Model):
    """Ontology Source Reference (ISA-Tab Spec 4.1.1)"""
    investigation = models.ForeignKey(Investigation)
    name = models.TextField(blank=True, null=True)
    file_name = models.TextField(blank=True, null=True)
    version = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.name) + " (" + str(self.file_name) + ")"


class Study(NodeCollection):
    investigation = models.ForeignKey(Investigation)
    # TODO: should we support an archive file here? (see ISA-Tab Spec 4.1.3.2)
    file_name = models.TextField()

    def get_dataset(self):
        investigation_uuid = self.investigation.uuid
        try:
            data_set = core.models.InvestigationLink.objects.filter(
                investigation__uuid=investigation_uuid
            ).order_by("version").reverse()[0].data_set
        except (AttributeError, IndexError) as e:
            raise RuntimeError(
                "Couldn't fetch DataSet for Investigation {}: {}".format(
                    investigation_uuid, e
                )
            )
        return data_set

    def __str__(self):
        return str(self.identifier) + ": " + str(self.title)


@receiver(pre_delete, sender=Study)
def _study_delete(sender, instance, **kwargs):
    """
    Removes a Study's related objects upon deletion being triggered.
    Having these extra checks is favored within a signal so that this logic
    is picked up on bulk deletes as well.

    See: https://docs.djangoproject.com/en/1.8/topics/db/models/
    #overriding-model-methods
    """
    Node.objects.filter(study=instance).delete()


class Design(models.Model):
    """Study Design Descriptor (ISA-Tab Spec 4.1.3.2)"""
    study = models.ForeignKey(Study)
    type = models.TextField(blank=True, null=True)
    type_accession = models.TextField(blank=True, null=True)
    type_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.type)


class Factor(models.Model):
    """Study Factor (ISA-Tab Spec 4.1.3.4)"""
    study = models.ForeignKey(Study)
    name = models.TextField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    type_accession = models.TextField(blank=True, null=True)
    type_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.name) + ": " + str(self.type)


class Assay(models.Model):
    """Study Assay (ISA-Tab Spec 4.1.3.5)"""
    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False,
                            unique=True)
    study = models.ForeignKey(Study)
    measurement = models.TextField(blank=True, null=True)
    measurement_accession = models.TextField(blank=True, null=True)
    measurement_source = models.TextField(blank=True, null=True)
    technology = models.TextField(blank=True, null=True)
    technology_accession = models.TextField(blank=True, null=True)
    technology_source = models.TextField(blank=True, null=True)
    platform = models.TextField(blank=True, null=True)
    file_name = models.TextField()

    def __str__(self):
        retstr = ""
        if self.measurement:
            retstr += "Measurement: %s; " % str(self.measurement)

        if self.technology:
            retstr += "Technology: %s; " % str(self.technology)

        if self.platform:
            retstr += "Platform: %s; " % str(self.platform)

        retstr += "File: %s" % str(self.file_name)
        return retstr

    def get_file_count(self):
        return Node.objects.filter(
            assay=self,
            file_item__isnull=False,
            is_auxiliary_node=False
        ).count()


class Protocol(models.Model):
    """Study Protocol (ISA-Tab Spec 4.1.3.6)"""
    study = models.ForeignKey(Study)
    uuid = UUIDField(unique=True, auto=True)
    # workflow_uuid can be used to associate the protocol with a workflow
    # TODO: should this be the analysis uuid? (problem: technically an analysis
    # is the execution of a protocol)
    workflow_uuid = UUIDField(unique=True, auto=True)
    version = models.TextField(blank=True, null=True)
    name = models.TextField(blank=True, null=True)
    name_accession = models.TextField(blank=True, null=True)
    name_source = models.TextField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    type_accession = models.TextField(blank=True, null=True)
    type_source = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    uri = models.TextField(blank=True, null=True)
    # protocol parameters: via FK
    # protocol components: via FK

    def __str__(self):
        return str(self.name) + ": " + str(self.type)

    class Meta:
        ordering = ['id']


class ProtocolParameter(models.Model):
    study = models.ForeignKey(Study)
    protocol = models.ForeignKey(Protocol)
    name = models.TextField(blank=True, null=True)
    name_accession = models.TextField(blank=True, null=True)
    name_source = models.TextField(blank=True, null=True)


class ProtocolComponent(models.Model):
    study = models.ForeignKey(Study)
    protocol = models.ForeignKey(Protocol)
    name = models.TextField(blank=True, null=True)
    type = models.TextField(blank=True, null=True)
    type_accession = models.TextField(blank=True, null=True)
    type_source = models.TextField(blank=True, null=True)


class Node(models.Model):
    # allowed node types
    SOURCE = "Source Name"
    SAMPLE = "Sample Name"
    EXTRACT = "Extract Name"
    LABELED_EXTRACT = "Labeled Extract Name"

    SCAN = "Scan Name"
    NORMALIZATION = "Normalization Name"
    DATA_TRANSFORMATION = "Data Transformation Name"

    ASSAY = "Assay Name"
    HYBRIDIZATION_ASSAY = "Hybridization Assay Name"
    GEL_ELECTROPHORESIS_ASSAY = "Gel Electrophoresis Assay Name"
    NMR_ASSAY = "NMR Assay Name"
    MS_ASSAY = "MS Assay Name"

    ARRAY_DESIGN_FILE = "Array Design File"
    ARRAY_DESIGN_FILE_REF = "Array Design File REF"
    IMAGE_FILE = "Image File"
    RAW_DATA_FILE = "Raw Data File"
    DERIVED_DATA_FILE = "Derived Data File"
    ARRAY_DATA_FILE = "Array Data File"
    DERIVED_ARRAY_DATA_FILE = "Derived Array Data File"
    ARRAY_DATA_MATRIX_FILE = "Array Data Matrix File"
    DERIVED_ARRAY_DATA_MATRIX_FILE = "Derived Array Data Matrix File"
    SPOT_PICKING_FILE = "Spot Picking File"
    RAW_SPECTRAL_DATA_FILE = "Raw Spectral Data File"
    DERIVED_SPECTRAL_DATA_FILE = "Derived Spectral Data File"
    PEPTIDE_ASSIGNMENT_FILE = "Peptide Assignment File"
    PROTEIN_ASSIGNMENT_FILE = "Protein Assignment File"
    PTM_ASSIGNMENT_FILE = "Post Translational Modification Assignment File"
    FREE_INDUCTION_DECAY_DATA_FILE = "Free Induction Decay Data File"
    ACQUISITION_PARAMETER_DATA_FILE = "Aquisition Parameter Data File"
    METABOLITE_ASSIGNMENT_FILE = "Metabolite Assignment File"

    ASSAYS = {
        ASSAY,
        HYBRIDIZATION_ASSAY,
        MS_ASSAY,
        NMR_ASSAY,
        GEL_ELECTROPHORESIS_ASSAY
    }

    FILES = {
        ARRAY_DESIGN_FILE,
        ARRAY_DESIGN_FILE_REF,
        IMAGE_FILE,
        RAW_DATA_FILE,
        DERIVED_DATA_FILE,
        ARRAY_DATA_FILE,
        DERIVED_ARRAY_DATA_FILE,
        ARRAY_DATA_MATRIX_FILE,
        DERIVED_ARRAY_DATA_MATRIX_FILE,
        SPOT_PICKING_FILE,
        RAW_SPECTRAL_DATA_FILE,
        DERIVED_SPECTRAL_DATA_FILE,
        PEPTIDE_ASSIGNMENT_FILE,
        PROTEIN_ASSIGNMENT_FILE,
        PTM_ASSIGNMENT_FILE,
        FREE_INDUCTION_DECAY_DATA_FILE,
        ACQUISITION_PARAMETER_DATA_FILE,
        METABOLITE_ASSIGNMENT_FILE
    }

    INDEXED_FILES = {
        RAW_DATA_FILE, DERIVED_DATA_FILE,
        ARRAY_DATA_FILE, DERIVED_ARRAY_DATA_FILE,
        ARRAY_DATA_MATRIX_FILE, DERIVED_ARRAY_DATA_MATRIX_FILE
    }

    TYPES = ASSAYS | FILES | {
        SOURCE, SAMPLE, EXTRACT, LABELED_EXTRACT, SCAN, NORMALIZATION,
        DATA_TRANSFORMATION}
    # Currently we only need to create an auxiliary file for bam, but WIG
    # needs an index file as well
    AUXILIARY_FILES_NEEDED_FOR_VISUALIZATION = ['bam']

    uuid = UUIDField(unique=True, auto=True)
    study = models.ForeignKey(Study, db_index=True)
    assay = models.ForeignKey(Assay, db_index=True, blank=True, null=True)
    children = models.ManyToManyField('self', symmetrical=False,
                                      related_name='parents_set')
    parents = models.ManyToManyField('self', symmetrical=False,
                                     related_name='children_set')
    type = models.TextField(db_index=True)
    name = models.TextField(db_index=True)
    # only used for nodes representing files
    file_item = models.ForeignKey(FileStoreItem, null=True, default=None,
                                  on_delete=models.SET_NULL)
    # Refinery internal "attributes" (exported as comment attributes)
    genome_build = models.TextField(db_index=True, null=True)
    species = models.IntegerField(db_index=True, null=True)
    is_annotation = models.BooleanField(default=False)
    analysis_uuid = UUIDField(default=None, blank=True, null=True, auto=False)
    is_auxiliary_node = models.BooleanField(default=False)
    subanalysis = models.IntegerField(null=True, blank=False)
    workflow_output = models.CharField(null=True, blank=False, max_length=500)

    def __str__(self):
        return str(self.type) + ": " + str(self.name) + " (" +\
               str(self.parents.count()) + " parents, " +\
               str(self.children.count()) + " children " + "| " +\
               "species: " + str(self.species) +\
               ", genome build: " + str(self.genome_build) + ")"

    def add_child(self, node):
        if node is None:
            return None
        self.children.add(node)
        self.save()
        node.parents.add(self)
        node.save()
        return self

    def get_analysis(self):
        try:
            return core.models.Analysis.objects.get(uuid=self.analysis_uuid)
        except core.models.Analysis.DoesNotExist:
            return None
        except core.models.Analysis.MultipleObjectsReturned as e:
            logger.error("Multiple Analyses found for Node with UUID: %s %s",
                         self.uuid, e)
            return None

    def _get_derived_node_types(self):
        """
        This finds all node types which are "derived"
        :returns: a list of all node types which are "derived"
        """
        derived_node_types = []

        for item in self.FILES:
            if "derived" in item.lower():
                derived_node_types.append(item)

        return derived_node_types

    def is_derived(self):
        """
        This is a helper method to aid in the checking of if a Node has
        been analyzed further when we delete an Analysis.
        :returns True if the node in question's type exists in the list of
        Node types which are "derived"
        """
        return self.type in self._get_derived_node_types()

    def is_orphan(self):
        return self.parents.count() == 0

    def get_analysis_node_connections(self):
        return core.models.AnalysisNodeConnection.objects.filter(node=self)

    def create_and_associate_auxiliary_node(self, filestore_item):
            """
            Tries to create and associate an auxiliary Node with a parent
            node.

            If said auxiliary Node already exists, we just do a get()
            and do not re-add it as a child
            """
            node = Node.objects.get_or_create(
                study=self.study, assay=self.assay,
                name="auxiliary Node for: {}".format(self.name),
                is_auxiliary_node=True, file_item=filestore_item
            )
            # get_or_create() returns a tuple:
            # (<Node_object>, Boolean: <created>)
            # So, if this Node is newly created, we will associate it as a
            # child to its parent, otherwise nothing happens
            # https://docs.djangoproject.com/en/1.10/ref/models/querysets/#get-or-create
            node_object = node[0]
            is_newly_created_node = node[1]

            if is_newly_created_node:
                self.add_child(node_object)
                return node_object

    def get_children(self):
        """
        Return a list of child Node's uuids for a given Node
        """
        return [child.uuid for child in self.children.all()]

    def get_parents(self):
        """
        Return a list of parent Node's uuids for a given Node
        """
        return [parent.uuid for parent in self.parents.all()]

    def get_auxiliary_node_uuids(self):
        """
        Return a list of uuids of auxiliary Nodes for a Given Node
        """
        child_nodes = self.get_children()
        aux_nodes = []
        for uuid in child_nodes:
            try:
                node = Node.objects.get(uuid=uuid)
                if node.is_auxiliary_node:
                    aux_nodes.append(node.uuid)
            except (Node.DoesNotExist, Node.MultipleObjectsReturned) as e:
                logger.error(e)

        return aux_nodes

    def is_auxiliary_node_needed(self):
        return self.file_item and self.file_item.filetype and \
                self.file_item.filetype.used_for_visualization and \
                self.file_item.datafile and \
                settings.REFINERY_AUXILIARY_FILE_GENERATION == \
                'on_file_import' and \
                self.file_item.get_extension().lower() in \
                self.AUXILIARY_FILES_NEEDED_FOR_VISUALIZATION

    def generate_auxiliary_node_task(self):
        """This method is initiated after a task_success signal is returned
        from the file import task.  It generates the tasks for creating an
        auxiliary file and importing it into refinery.  Use
        is_auxiliary_node_needed() to check if this should be run before
        running it.
        """

        generate = data_set_manager.tasks.generate_auxiliary_file.subtask(
            (self.uuid,)
        )
        file_import = FileImportTask().subtask()
        return chain(generate, file_import)

    def get_auxiliary_file_generation_task_state(self):
        """Return the generate_auxiliary_file task state for a given auxiliary
        Node or None if a regular Node
        """
        if self.is_auxiliary_node:
            return AsyncResult(self.file_item.import_task_id).state
        else:
            return None

    def update_solr_index(self):
        data_set_manager.search_indexes.NodeIndex().update_object(
            self, using="data_set_manager"
        )


@receiver(pre_delete, sender=Node)
def _node_delete(sender, instance, *args, **kwargs):
    """Removes a Node's related objects upon deletion being triggered
    Having these extra checks is favored within a signal so that this logic
    is picked up on bulk deletes as well
    https://docs.djangoproject.com/en/1.8/topics/db/models/#overriding-model-methods
    """
    if instance.file_item:
        instance.file_item.delete()
    delete_analysis_index(instance)


class Attribute(models.Model):
    # allowed attribute types
    MATERIAL_TYPE = "Material Type"
    CHARACTERISTICS = "Characteristics"
    FACTOR_VALUE = "Factor Value"
    LABEL = "Label"
    COMMENT = "Comment"

    editable_types = [MATERIAL_TYPE, CHARACTERISTICS, FACTOR_VALUE, LABEL,
                      COMMENT]

    TYPES = {MATERIAL_TYPE, CHARACTERISTICS, FACTOR_VALUE, LABEL, COMMENT}

    ALL_FIELDS = [
        "id",
        "type",
        "subtype",
        "value",
        "value_unit",
        "value_accession",
        "value_source",
        "node"
    ]
    NON_ONTOLOGY_FIELDS = [
        "id",
        "type",
        "subtype",
        "value",
        "value_unit",
        "node"
    ]

    node = models.ForeignKey(Node, db_index=True)
    type = models.TextField(db_index=True)
    # subtype further qualifies the attribute type, e.g. type = factor value
    # and subtype = age
    subtype = models.TextField(blank=True, null=True, db_index=True)
    value = models.TextField(blank=True, null=True, db_index=True)
    value_unit = models.TextField(blank=True, null=True)
    # if value_unit is not null value is numeric and value_accession and
    # value_source refer to value_unit (rather than value)
    value_accession = models.TextField(blank=True, null=True)
    value_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return (
            str(self.type) + (
                "" if self.subtype is None else " (" + str(
                    self.subtype
                ) + ")"
            ) +
            " = " +
            str(self.value)
        )


# non-ISA Tab
class AttributeOrder(models.Model):
    study = models.ForeignKey(Study, db_index=True)
    assay = models.ForeignKey(Assay, db_index=True, blank=True, null=True)
    solr_field = models.TextField(db_index=True)
    # position of the attribute in the facet list and table
    rank = models.IntegerField(blank=True, null=True)
    # should this attribute be exposed to the user? if false the attribute will
    # never be shown to non-owner users
    is_exposed = models.BooleanField(default=True)
    # should this attribute be used as a facet?
    is_facet = models.BooleanField(default=True)
    # should be shown in the table by default?
    is_active = models.BooleanField(default=True)
    # is this an internal attribute? (retrieved by solr by never exposed to any
    # user)
    is_internal = models.BooleanField(default=False)

    def __str__(self):
        return str(
            self.solr_field +
            " [facet = " +
            str(self.is_facet) +
            " exp = " +
            str(self.is_exposed) +
            " act = " +
            str(self.is_active) +
            " int = " + str(self.is_internal) + "] = "
        ) + str(self.rank)


class AnnotatedNodeRegistry(models.Model):
    study = models.ForeignKey(Study)
    assay = models.ForeignKey(Assay, blank=True, null=True)
    node_type = models.TextField()
    creation_date = models.DateTimeField(auto_now_add=True)
    modification_date = models.DateTimeField(auto_now=True)


class AnnotatedNode(models.Model):
    node = models.ForeignKey(Node, db_index=True)
    attribute = models.ForeignKey(Attribute)
    study = models.ForeignKey(Study)
    assay = models.ForeignKey(Assay, blank=True, null=True)
    node_uuid = UUIDField()
    node_file_uuid = UUIDField(blank=True, null=True)
    node_type = models.TextField()
    node_name = models.TextField()
    attribute_type = models.TextField()
    # subtype further qualifies the attribute type, e.g. type = factor value
    # and subtype = age
    attribute_subtype = models.TextField(blank=True, null=True)
    attribute_value = models.TextField(blank=True, null=True)
    attribute_value_unit = models.TextField(blank=True, null=True)
    # genome information
    node_species = models.IntegerField(null=True)
    node_genome_build = models.TextField(null=True)
    node_analysis_uuid = UUIDField(
        default=None,
        blank=True,
        null=True,
        auto=False
    )
    node_subanalysis = models.IntegerField(null=True, blank=False)
    node_workflow_output = models.CharField(
        null=True,
        blank=False,
        max_length=100
    )
    # other information
    is_annotation = models.BooleanField(default=False)

    def __str__(self):
        return str(self.node_uuid)


def _is_internal_attribute(attribute):
    return attribute in ["uuid",
                         "study_uuid",
                         "assay_uuid",
                         "file_uuid",
                         "type",
                         "is_annotation",
                         "species",
                         "genome_build",
                         "name",
                         "analysis_uuid",
                         "subanalysis",
                         "output_type"]


def _is_active_attribute(attribute):
    return not _is_internal_attribute(attribute)


def _is_exposed_attribute(attribute):
    return True


def _is_ignored_attribute(attribute):
    """Ignore Django internal Solr fields"""
    return attribute in ["django_ct", "django_id", "id"]


def _query_solr(study, assay, attribute=None):
    types = ' OR '.join(
        '"{0}"'.format(type) for type in Node.FILES
    )

    url = '{base_url}data_set_manager/select'.format(
        base_url=settings.REFINERY_SOLR_BASE_URL
    )

    params = {
        'fq': 'study_uuid:{study_uuid} AND '
              'assay_uuid: {assay_uuid} AND '
              'is_annotation:false AND '
              'type:({types})'.format(
                  study_uuid=study.uuid,
                  assay_uuid=assay.uuid,
                  types=types
              ),
        'q': 'django_ct:data_set_manager.node',
        'rows': 1,
        'start': 0,
        'wt': 'json'
    }

    if attribute is not None:
        params.update({
            'facet': 'true',
            'facet.field': attribute,
            'facet.sort': 'count',
            'facet.limit': '-1'
        })

    # This log tends to be massive and spams the log file. Turn on only when
    # needed.
    # logger.debug('Query parameters: %s', params)

    headers = {'Accept': 'application/json'}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
    except HTTPError as e:
        logger.error(e)
        raise

    results = response.json()

    # This log tends to be massive and spams the log file. Turn on only when
    # needed.
    # logger.debug('Query results: %s', results)

    if results['response']['numFound'] == 0:
        raise ValueError('No results.')

    return results


def _is_facet_attribute(attribute, study, assay):
    """Tests if a an attribute should be used as a facet by default.
    :param attribute: The name of the attribute.
    :type attribute: string
    :returns: True if the ratio between items in the data set and the number of
    facet attribute values is smaller than
    settings.DEFAULT_FACET_ATTRIBUTE_VALUES_RATIO, false otherwise.
    """
    # download_url custom attribute which should not be treated as a facet
    if data_set_manager.search_indexes.NodeIndex.DOWNLOAD_URL == attribute:
        return False

    ratio = 0.5
    results = _query_solr(attribute=attribute, study=study, assay=assay)
    items = results['response']['numFound']
    attribute_values = len(
        results['facet_counts']['facet_fields'][attribute]
    ) / 2
    return (attribute_values / items) < ratio


@skip_if_test_run
def initialize_attribute_order(study, assay):
    """Initializes the AttributeOrder table after all nodes for the given study
    and assay have been indexed by Solr.
    :param study: Study object to query for in AnnotatedNode.
    :type study: Study
    :param assay: Assay object to query for in AnnotatedNode.
    :type assay: Assay
    :returns: Number of attributes that were indexed.
    """
    results = _query_solr(study=study, assay=assay)

    attribute_order_objects = []
    for key in results['response']['docs'][0]:
        is_facet = _is_facet_attribute(key, study, assay)
        is_exposed = _is_exposed_attribute(key)
        is_internal = _is_internal_attribute(key)
        is_active = _is_active_attribute(key)
        if not _is_ignored_attribute(key):
            attribute_order_objects.append(
                AttributeOrder(
                    study=study,
                    assay=assay,
                    solr_field=key,
                    rank=0,
                    is_facet=is_facet,
                    is_exposed=is_exposed,
                    is_internal=is_internal,
                    is_active=is_active
                )
            )
    # insert AttributeOrder objects into database
    AttributeOrder.objects.bulk_create(attribute_order_objects)

    return len(attribute_order_objects)


class ProtocolReference(models.Model):
    node = models.ForeignKey(Node)
    protocol = models.ForeignKey(Protocol)
    performer = models.TextField(blank=True, null=True)
    # performer_uuid can be used to associate the execution with a user account
    performer_uuid = UUIDField(blank=True, null=True)
    date = models.DateField(blank=True, null=True)
    comment = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.protocol) + " (reference)"


class ProtocolReferenceParameter(models.Model):
    protocol_reference = models.ForeignKey(ProtocolReference)
    name = models.TextField(blank=True, null=True)
    value = models.TextField(blank=True, null=True)
    value_unit = models.TextField(blank=True, null=True)
    # if value_unit is not null value is numeric and value_accession and
    # value_source refer to value_unit (rather than value)
    value_accession = models.TextField(blank=True, null=True)
    value_source = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.name) + " = " + str(self.value)
