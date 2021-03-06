# -*- coding: utf-8 -*-
# pylint: disable=W0621
import pytest
from unittestzero import Assert
from time import time, sleep


@pytest.fixture
def setup_soap_create_vm(
        request,
        soap_client,
        db,
        server_roles,
        provisioning_data_basic_only,
        vmware_linux_setup_data):
    '''Sets up first VM for clone/retirement tests'''
    vm_table = db.table('vms')

    # Check if VM already exists
    for name, guid, power_state in db.session.query(
            vm_table.name, vm_table.guid, vm_table.power_state).filter(
            vm_table.template is False):
        if vmware_linux_setup_data['vm_name'] in name:
            # VM exists
            print "VM exits"
            if power_state == 'on':
                result = soap_client.service.EVMSmartStop(guid)
                Assert.equal(result.result, 'true')
            break
    else:
        # Find template guid
        template_guid = None
        for name, guid in db.session.query(vm_table.name, vm_table.guid)\
                .filter(vm_table.template is True):
            if provisioning_data_basic_only['template'] in name:
                template_guid = guid.strip()
                break
        else:
            raise Exception("Couldn't find CFME template for provisioning smoke test")
        Assert.not_none(template_guid)

        # Generate provision request
        template_fields = soap_client.pipeoptions({
            'guid': template_guid,
        })

        # VMWare
        vm_fields = soap_client.pipeoptions({
            'number_of_cpu': vmware_linux_setup_data['number_of_cpu'],
            'vm_memory': vmware_linux_setup_data['vm_memory'],
            'vm_name': vmware_linux_setup_data['vm_name']
        })

        requester = soap_client.pipeoptions({
            'owner_first_name': vmware_linux_setup_data['owner_first_name'],
            'owner_last_name': vmware_linux_setup_data['owner_last_name'],
            'owner_email': vmware_linux_setup_data['owner_email'],
        })

        result = soap_client.service.VmProvisionRequest('1.1',
            template_fields, vm_fields, requester, '', '')
        request_id = result.id
        Assert.not_none(request_id)

        # Poll for VM to be provisioned
        start_time = time()
        vm_guid = None
        while (time() - start_time < 300):  # Give EVM 5 mins to change status
            result = soap_client.service.GetVmProvisionRequest(request_id)
            if result.approval_state == 'approved':
                if result.status == 'Error':
                    pytest.fail(result.message)

                Assert.equal(result.status, 'Ok')

                if result.request_state == 'finished':
                    while not vm_guid:
                        sleep(10)
                        result = soap_client.service.GetVmProvisionRequest(request_id)
                        if result.vms[0]:
                            vm_guid = result.vms[0].guid
                    break
            sleep(30)

        Assert.not_none(vm_guid)
        result = soap_client.service.FindVmByGuid(vm_guid)
        Assert.equal(result.name, vmware_linux_setup_data['vm_name'])
        Assert.equal(result.guid, vm_guid)
        result = soap_client.service.EVMSmartStop(vm_guid)
        Assert.equal(result.result, 'true')
