import time
from django.core.management.base import BaseCommand
from server.maintenance import delete_expired_anonymous_workflows
from server.updates import update_wfm_data_scan
from server.utils import get_console_logger


_logger = get_console_logger()


class Command(BaseCommand):
    help = 'Continually deletes expired anonymous workflows and polls wfmodules for updates'

    def handle(self, *args, **options):
        while True:
            try:
                update_wfm_data_scan()
            except Exception as err:
                _logger.exception(err)

            try:
                delete_expired_anonymous_workflows()
            except Exception as err:
                _logger.exception(err)

            time.sleep(60)
