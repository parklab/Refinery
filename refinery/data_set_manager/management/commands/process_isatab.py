from celery.task.sets import TaskSet
from data_set_manager.tasks import parse_isatab
from django.core.management.base import BaseCommand, CommandError
from optparse import make_option
import os
import re
import sys
import logging

# get module logger
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = """
    Takes the directory of an ISA-Tab file as input, parses, and inputs it into
    the database\n\nUsage: python manage.py process_isatab <username> <isatab
    directory or file> [--base_pre_isa_dir <base pre-isatab directory or file>
    --public --file_base_path <base path if file locations are relative>]\n
    """

    option_list = BaseCommand.option_list + (
        make_option('--base_pre_isa_dir',
                    action='store',
                    type='string'
                    ),
        make_option('--file_base_path',
                    action='store',
                    type='string',
                    default=None
                    ),
        make_option('--public',
                    action='store_true',
                    default=False
                    ),
        )

    """
    Name: handle
    Description:
        main program; calls the parsing and insertion functions
    """
    _username = None
    _additional_raw_data_file_extension = None

    def __init__(self, filename=None):
        super(Command, self).__init__()

    def handle(self, username, base_isa_dir, **options):
        try:
            self._username = username
        except:
            raise CommandError(self.help)

        """
        Get a list of all the isatab files in base_isa_dir.
        """
        isatab_dict = dict()
        for root, dirs, filenames in os.walk(base_isa_dir):
            for filename in filenames:
                isatab_dict[filename] = [os.path.join(root, filename)]

        """
        If isatab_dict is empty, then base_isa_dir is a file, not a directory.
        """
        if not isatab_dict:
            isatab_dict[base_isa_dir] = [base_isa_dir]

        """
        Get a list of all the isatab files in base_pre_isa_dir.
        """
        pre_isatab_files = 0
        try:
            for root, dirs, filenames in os.walk(options['base_pre_isa_dir']):
                for filename in filenames:
                    """
                    Associate pre-isatab file with isatab file.
                    """
                    for key in isatab_dict:
                        if re.search(r'%s$' % key, filename):
                            file = os.path.join(root, filename)
                            isatab_dict[key].append(file)
                            pre_isatab_files += 1
                            break
        except:
            pass

        """
        If base_pre_isa_dir is defined but pre_isatab_files is 0,
        then base_pre_isa_dir is a pre-ISA-Tab archive, not a directory
        """
        if options['base_pre_isa_dir'] and not pre_isatab_files:
            isatab_dict[base_isa_dir].append(options['base_pre_isa_dir'])

        s_tasks = list()
        """
        Add subtasks to list
        """
        for k, v_list in isatab_dict.items():
            isa_file = v_list.pop(0)
            try:
                pre_file = v_list.pop(0)
            except:
                pre_file = None

            sub_task = parse_isatab.subtask(
                args=(
                    self._username,
                    options['public'],
                    isa_file,
                    self._additional_raw_data_file_extension,
                    isa_file, pre_file,
                    options['file_base_path']
                )
            )
            s_tasks.append(sub_task)

        job = TaskSet(tasks=s_tasks)
        result = job.apply_async()

        task_num = 1
        total = len(isatab_dict)
        for (i, filename) in result.iterate():
            try:
                if i:
                    print (
                        "{num} / {total}: Successfully parsed {file} into "
                        "DataSet with UUID {uuid}".format(
                            num=task_num,
                            total=total,
                            file=filename,
                            uuid=i
                        )
                    )
                else:
                    print (
                        "{num} / {total}: Skipped {file} as it has been "
                        "successfully parsed already".format(
                            num=task_num,
                            total=total,
                            file=filename
                        )
                    )
                task_num += 1
                sys.stdout.flush()
            except:
                print (
                    "{num} / {total}: Unsuccessful parsed {file}".format(
                        num=task_num,
                        total=total,
                        file=filename
                    )
                )
                task_num += 1
                sys.stdout.flush()
