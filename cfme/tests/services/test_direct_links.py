# -*- coding: utf-8 -*-
"""Tests checking for link access from outside."""
import pytest
import random

from cfme.fixtures import pytest_selenium as sel
from cfme.infrastructure.provisioning import provisioning_form
from cfme.services import requests
from cfme.web_ui import flash
from utils.browser import browser
from utils.conf import cfme_data, env
from utils.providers import list_infra_providers, setup_provider
from utils.randomness import generate_random_string
from utils.wait import TimedOutError, wait_for


pytestmark = [
    pytest.mark.fixtureconf(server_roles="-automate"),  # To prevent the provisioning itself.
    pytest.mark.usefixtures('server_roles')
]


@pytest.fixture(scope="module")
def provider_id():
    """Select provider which is not RHEV"""
    return random.choice([p_id for p_id in list_infra_providers() if not p_id.startswith("rhev")])


@pytest.fixture(scope="module")
def provider_data(provider_id):
    return cfme_data["management_systems"][provider_id]


@pytest.fixture(scope="module")
def provider(provider_id):
    return setup_provider(provider_id)


@pytest.yield_fixture(scope="module")
def generated_request(provider, provider_data, provider_id):
    """Creates a provision request, that is not automatically approved, and returns the search data.

    After finishing the test, request should be automatically deleted.

    Slightly modified code from :py:module:`cfme.tests.infrastructure.test_provisioning`
    """
    vm_name = generate_random_string()
    first_name = generate_random_string()
    last_name = generate_random_string()
    notes = generate_random_string()
    e_mail = "{}@{}.test".format(first_name, last_name)
    provisioning = provider_data.get("provisioning", {})
    template, host, datastore = map(provisioning.get, ('template', 'host', 'datastore'))
    pytest.sel.force_navigate('infrastructure_provision_vms', context={
        'provider': provider,
        'template_name': template,
    })

    provisioning_data = {
        'email': e_mail,
        'first_name': first_name,
        'last_name': last_name,
        'notes': notes,
        'vm_name': vm_name,
        'host_name': {'name': [host]},
        'datastore_name': {'name': [datastore]},
        'num_vms': "10",    # so it won't get auto-approved
    }

    # Same thing, different names. :\
    if provider_data["type"] == 'rhevm':
        provisioning_data['provision_type'] = 'Native Clone'
    elif provider_data["type"] == 'virtualcenter':
        provisioning_data['provision_type'] = 'VMware'

    try:
        provisioning_data['vlan'] = provisioning['vlan']
    except KeyError:
        # provisioning['vlan'] is required for rhevm provisioning
        if provider_data["type"] == 'rhevm':
            raise pytest.fail('rhevm requires a vlan value in provisioning info')

    provisioning_form.fill(provisioning_data)
    pytest.sel.click(provisioning_form.submit_button)
    flash.assert_no_errors()
    request_cells = {
        "Description": "Provision from [{}] to [{}###]".format(template, vm_name),
    }
    yield request_cells
    browser().get(env["base_url"])
    requests.delete_request(request_cells)
    flash.assert_no_errors()


def test_services_request_direct_url(generated_request):
    """Go to the request page, save the url and try to access it directly."""
    assert requests.go_to_request(generated_request), "could not find the request!"
    request_url = sel.current_url()
    sel.get(env["base_url"])    # I need to flip it with something different here
    sel.get(request_url)        # Ok, direct access now.
    # This is a bit tricky. We have to wait IF the blank page appeared, because checking
    # if we are STILL IN CFME is unreliable as the transition is not guarded by JS or stuff.
    # btw. when the on_cfme_page returns true because of being on login screen, it will work.
    # After logging in, user is redirected for a correct link. Tested.
    try:
        wait_for(
            lambda: not sel.on_cfme_page(),
            num_sec=20,
            message="wait for blank page appear"
        )
        pytest.fail("Blank screen appeared!")
    except TimedOutError:
        pass  # Success!
