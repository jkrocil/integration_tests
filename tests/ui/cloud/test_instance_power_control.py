# -*- coding: utf-8 -*-

import random
import time

import pytest
from unittestzero import Assert

from utils.conf import cfme_data
from utils.providers import cloud_provider_type_map
from utils.wait import wait_for

pytestmark = [pytest.mark.nondestructive,
              pytest.mark.usefixtures("setup_cloud_providers")]


def fetch_list(data):
    tests = []
    for provider in data["management_systems"]:
        prov_data = data['management_systems'][provider]
        if prov_data["type"] in cloud_provider_type_map:

            # technically cloud instances are stateless, opting to just provision a instance to
            #  test with
            if prov_data["small_template"] is not None:
                tests.append(['', provider, prov_data["small_template"]])
    return tests


def pytest_generate_tests(metafunc):
    argnames = []
    tests = []

    if 'get_image' in metafunc.fixturenames:
        argnames = ['get_image', 'provider', 'image_name']
        metafunc.parametrize(argnames, fetch_list(cfme_data), scope="module")
    elif 'random_provider_image' in metafunc.fixturenames:
        argnames = ['random_provider_image', 'provider', 'image_name']
        all_tests = fetch_list(cfme_data)
        if all_tests:
            tests.append(random.choice(all_tests))
        metafunc.parametrize(argnames, tests, scope="module")


@pytest.mark.usefixtures("get_image")
class TestInstanceDetailsPowerControlPerProvider:

    def test_terminate(
            self,
            cfme_data,
            provider,
            image_name,
            mgmt_sys_api_clients,
            cloud_providers_pg,
            random_string):
        """Test terminate operation from a instance details page.
        Verify instance is archived."""

        prov_data = cfme_data["management_systems"][provider]
        if prov_data["type"] == 'openstack':
            if 'network' in prov_data:
                mgmt_sys_api_clients[provider].deploy_template(image_name, flavour_name='m1.small',
                                                               vm_name=random_string,
                                                               network_name=prov_data['network'])
            else:
                mgmt_sys_api_clients[provider].deploy_template(image_name, flavour_name='m1.small',
                                                               vm_name=random_string)
        else:
            random_string = mgmt_sys_api_clients[provider].deploy_template(
                image_name, instance_type='t1.micro')

        provider_details = cloud_providers_pg.load_provider_details(prov_data["name"])
        time.sleep(30)
        provider_details.click_on_refresh_relationships()
        # cfme issue where if detail value == 0 , its not a link so wait for the refresh to finish
        wait_for(lambda: provider_details.details.get_section('Relationships')
                 .get_item('Instances').value,
                 fail_condition="0",
                 fail_func=pytest.sel.refresh,
                 delay=15,
                 num_sec=300)
        inst_list_pg = provider_details.all_instances()
        inst_details = inst_list_pg.find_instance_page(random_string, None, False, True, 15)
        inst_details.wait_for_instance_state_change('on', 12)
        inst_details.power_button.terminate()
        if prov_data["type"] == 'openstack':
            time.sleep(60)
            Assert.false(mgmt_sys_api_clients[provider].does_vm_exist(random_string))
        else:
            # ec2 terminated instance shutsdown and stays in terminate status for a bit
            count = 0
            while mgmt_sys_api_clients[provider].vm_status(random_string) != 'terminated' and \
                    count < 10:
                time.sleep(30)
                count += 1
            Assert.equal(str(mgmt_sys_api_clients[provider].vm_status(random_string)), 'terminated')
