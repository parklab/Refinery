"""
* Manages all data files
* Downloads files from external sources (by URL)

"""

import logging
import os
import re

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

import botocore
import celery
from django_extensions.db.fields import UUIDField

import constants
import core

logger = logging.getLogger(__name__)


def _map_source(source):
    """Convert URLs to file system paths by applying file source map"""
    for pattern, replacement in \
            settings.REFINERY_FILE_SOURCE_MAP.items():
        translated_source = re.sub(pattern, replacement, source)
        if translated_source != source:
            return translated_source
    return source


def generate_file_source_translator(username=None, base_path=None,
                                    identity_id=None):
    """Generate a relative source path translator function based on username
    or base path or AWS Cognito identity ID

    username: user's subdirectory in settings.REFINERY_DATA_IMPORT_DIR
    base_path: absolute path to prepend to source if source is relative
    identity_id: AWS Cognito identity ID of the current user
    """

    def translate(source):
        """Convert file source to absolute path

        source: URL, absolute or relative file system path
        """
        # ignore URLs and absolute file system paths as a failsafe
        if core.utils.is_absolute_url(source) or os.path.isabs(source):
            return source

        # process relative path
        if settings.REFINERY_DEPLOYMENT_PLATFORM == 'aws':
            source = "s3://{}/{}/{}".format(
                settings.UPLOAD_BUCKET, identity_id, source
            )
        elif base_path:
            source = os.path.join(base_path, source)
        elif username:
            source = os.path.join(
                settings.REFINERY_DATA_IMPORT_DIR, username, source)
        else:
            raise ValueError("Failed to translate relative source path: "
                             "must provide either username or base_path")
        return source

    return translate


class FileType(models.Model):
    name = models.CharField(unique=True, max_length=50)
    description = models.CharField(max_length=250)
    used_for_visualization = models.BooleanField(default=False)

    def __str__(self):
        return self.description if self.description else self.name


class FileExtension(models.Model):
    name = models.CharField(unique=True, max_length=50)
    filetype = models.ForeignKey(FileType)

    def __str__(self):
        return self.name


class FileStoreItem(models.Model):
    """Represents all data files"""
    datafile = models.FileField(blank=True, max_length=1024)
    uuid = UUIDField()  # auto-generated unique ID
    # URL, absolute file system path, or blank if source is a blob or similar
    source = models.CharField(blank=True, max_length=1024)
    filetype = models.ForeignKey(FileType, blank=True, null=True)
    # ID of Celery task used for importing the data file
    import_task_id = UUIDField(auto=False, blank=True)
    # Date created
    created = models.DateTimeField(auto_now_add=True)
    # Date updated
    updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.datafile.name:
            return self.datafile.name
        elif self.source:
            return self.source
        else:
            return str(self.uuid)  # UUID is available only after save()

    def save(self, *args, **kwargs):
        self.source = _map_source(self.source)

        if not self.filetype:
            # set file type using file extension
            try:
                extension = _get_file_extension(self.get_extension())
            except FileExtension.DoesNotExist as exc:
                logger.warn("Could not assign type to file '%s': %s",
                            self, exc)
            except FileExtension.MultipleObjectsReturned as exc:
                logger.critical("Could not assign type to file '%s': %s",
                                self, exc)
            else:
                self.filetype = extension.filetype

        super(FileStoreItem, self).save(*args, **kwargs)

    def get_file_size(self):
        """Return the size of the file in bytes or zero if the file is not
        available
        """
        try:
            return self.datafile.size
        except ValueError:  # no datafile
            return 0
        except (EnvironmentError, botocore.exceptions.BotoCoreError,
                botocore.exceptions.ClientError) as exc:
            # file is missing
            logger.critical("Error getting size for '%s': %s", self, exc)
            return 0

    def get_extension(self):
        """Return extension of datafile name or file name in source"""
        if self.datafile.name:
            return _get_extension_from_string(self.datafile.name)
        else:
            return _get_extension_from_string(self.source)

    def delete_datafile(self, save_instance=True):
        """Delete file from disk or S3 bucket and cancel file import"""
        self.terminate_file_import_task()
        if self.datafile:
            file_name = self.datafile.name
            try:
                self.datafile.delete(save=save_instance)
            except (EnvironmentError, botocore.exceptions.BotoCoreError,
                    botocore.exceptions.ClientError) as exc:
                logger.error("Error deleting file '%s': %s", file_name, exc)
            else:
                logger.info("Deleted datafile '%s'", file_name)

    def get_datafile_url(self):
        """Returns relative or absolute URL of the datafile depending on file
        availability and MEDIA_URL setting
        """
        try:
            return self.datafile.url
        except ValueError:  # no datafile
            if core.utils.is_absolute_url(self.source):
                if self.source.startswith('s3://'):
                    return None  # file is in the UPLOAD_BUCKET
                return self.source
            else:
                return None

    def get_import_status(self):
        """Return file import task state"""
        if not self.import_task_id:
            return constants.NOT_AVAILABLE
        return celery.result.AsyncResult(self.import_task_id).state

    def terminate_file_import_task(self):
        if self.import_task_id:
            logger.info("Terminating import task '%s' for '%s'",
                        self.import_task_id, self)
            result = celery.result.AsyncResult(self.import_task_id)
            result.revoke(terminate=True)

    def transfer_data_file(self, file_store_item):
        """
        Transfer the data file of a FileStoreItem to another FileStoreItem
        :param file_store_item: FileStoreItem instance to transfer the
        data file to
        """
        file_store_item.datafile = self.datafile
        file_store_item.save()
        # It's crucial to clear the datafile of the prior
        # FileStoreItem as well. Otherwise there would be two
        # references to the same data file which could cause
        # unintended side-effects
        self.datafile = None
        self.save()


# post_delete is safer than pre_delete
@receiver(post_delete, sender=FileStoreItem)
def _delete_datafile(sender, instance, **kwargs):
    """Delete the datafile when model is deleted
    Signal handler is required because QuerySet bulk delete does not call
    delete() method on the models
    """
    instance.delete_datafile(save_instance=False)


def _get_extension_from_string(path):
    """Return file extension given a file name, file system path, or URL"""
    file_name_parts = os.path.basename(path).split('.')
    if len(file_name_parts) == 1:  # no periods in file name
        return ''
    if len(file_name_parts) > 2:  # two or more periods in file name
        return '.'.join(file_name_parts[-2:])
    return file_name_parts[-1]  # one period in file name


def _get_file_extension(extension):
    """Return FileExtension object for a given file name or extension string"""
    try:
        return FileExtension.objects.get(name=extension)
    except FileExtension.DoesNotExist:
        if not extension:
            raise
        return _get_file_extension('.'.join(extension.split('.')[1:]))
