import asyncio
from unittest.mock import patch
from server.models import Delta, Tab, Workflow, WfModule
# We'll use ChangeWorkflowTitleCommand and ChangeWfModuleNotes as "canonical"
# deltas -- one requiring WfModule, one not.
from server.models.commands import ChangeWorkflowTitleCommand, \
        ChangeWfModuleNotesCommand
from ..utils import DbTestCase


future_none = asyncio.Future()
future_none.set_result(None)


@patch.object(Delta, 'schedule_execute', lambda *x: future_none)
@patch.object(Delta, 'ws_notify', lambda *x: future_none)
class DeltaTest(DbTestCase):
    def test_delete_orphans(self):
        workflow = Workflow.create_and_init()

        self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        delta2 = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='2')
        )
        delta3 = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='3')
        )
        self.run_with_async_db(delta3.backward())
        self.run_with_async_db(delta2.backward())
        # Create a new delta ... making delta2 and delta3 obsolete
        self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='4')
        )

        with self.assertRaises(Delta.DoesNotExist):
            delta2.refresh_from_db()
        with self.assertRaises(Delta.DoesNotExist):
            delta3.refresh_from_db()

    def test_delete_ignores_other_workflows(self):
        workflow = Workflow.create_and_init()
        workflow2 = Workflow.create_and_init()

        # Create a delta we want to delete
        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )

        # Create deltas on workflow2 that we _don't_ want to delete
        delta2 = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow2,
                                              new_value='1')
        )

        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        delta2.refresh_from_db()  # do not crash

    def test_delete_deletes_soft_deleted_wfmodule(self):
        workflow = Workflow.create_and_init()
        # Here's a soft-deleted module
        wf_module = workflow.tabs.first().wf_modules.create(
            order=0,
            module_id_name='foo',
            is_deleted=True
        )

        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        with self.assertRaises(WfModule.DoesNotExist):
            wf_module.refresh_from_db()

    def test_delete_deletes_soft_deleted_tab(self):
        workflow = Workflow.create_and_init()
        tab = workflow.tabs.create(position=1, is_deleted=True)
        # create a wf_module -- it needs to be deleted, too!
        wf_module = tab.wf_modules.create(order=0, module_id_name='foo',
                                          is_deleted=True)

        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        with self.assertRaises(WfModule.DoesNotExist):
            wf_module.refresh_from_db()
        with self.assertRaises(Tab.DoesNotExist):
            tab.refresh_from_db()

    def test_delete_protects_non_deleted_wfmodule(self):
        workflow = Workflow.create_and_init()
        # Here's a soft-deleted module
        wf_module = workflow.tabs.first().wf_modules.create(
            order=0,
            module_id_name='foo',
            is_deleted=False
        )

        # delete a delta
        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        wf_module.refresh_from_db()  # no DoesNotExist: it's not deleted

    def test_delete_protects_soft_deleted_wfmodule_with_reference(self):
        workflow = Workflow.create_and_init()
        # Here's a soft-deleted module
        wf_module = workflow.tabs.first().wf_modules.create(
            order=0,
            module_id_name='foo',
            is_deleted=True
        )

        # "protect" it: here's a delta we _aren't_ deleting
        self.run_with_async_db(
            ChangeWfModuleNotesCommand.create(workflow=workflow,
                                              wf_module=wf_module,
                                              new_value='1')
        )

        # now delete a delta
        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        wf_module.refresh_from_db()  # no DoesNotExist -- a delta depends on it

    def test_delete_scopes_wf_module_delete_by_workflow(self):
        workflow = Workflow.create_and_init()
        workflow2 = Workflow.create_and_init()
        # Here's a soft-deleted module on workflow2. Nothing references it. It
        # "shouldn't" exist.
        wf_module = workflow2.tabs.first().wf_modules.create(
            order=0,
            module_id_name='foo',
            is_deleted=True
        )

        # now delete a delta on workflow1
        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        wf_module.refresh_from_db()  # no DoesNotExist: leave workflow2 alone

    def test_delete_scopes_tab_delete_by_workflow(self):
        workflow = Workflow.create_and_init()
        workflow2 = Workflow.create_and_init()
        # Here's a soft-deleted module on workflow2. Nothing references it. It
        # "shouldn't" exist.
        tab = workflow2.tabs.create(position=1)

        # now delete a delta on workflow1
        delta = self.run_with_async_db(
            ChangeWorkflowTitleCommand.create(workflow=workflow, new_value='1')
        )
        self.run_with_async_db(delta.backward())  # fix workflow.last_delta_id
        delta.delete_with_successors()

        tab.refresh_from_db()  # no DoesNotExist: leave workflow2 alone
