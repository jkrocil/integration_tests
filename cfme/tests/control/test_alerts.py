#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import pytest

from cfme.control import explorer
from cfme.infrastructure import provider
from utils import testgen
from utils.log import logger
from utils.wait import wait_for


def pytest_generate_tests(metafunc):
    argnames, argvalues, idlist = testgen.infra_providers(metafunc, "test_vm_power_control")
    testgen.parametrize(metafunc, argnames, argvalues, ids=idlist, scope="module")


def wait_for_alert(smtp, alert, delay=None):
    """DRY waiting function

    Args:
        smtp: smtp_test funcarg
        alert: Alert name
        delay: Optional delay to pass to wait_for
    """
    logger.info("Waiting for informative e-mail of alert '%s' to come" % alert.description)
    wait_for(
        lambda: len(
            smtp.get_emails(
                subject_like="%%Alert Triggered: %s%%" % alert.description
            )
        ) > 0,
        num_sec=delay,
        delay=5,
        message="wait for e-mail to come!"
    )


def setup_for_alerts(request, alerts, event, vm_name, provider_data):
    """This function takes alerts and sets up CFME for testing it

    Args:
        request: py.test funcarg request
        alerts: Alert objects
        event: Event to hook on (VM Power On, ...)
        vm_name: VM name to use for policy filtering
        provider_data: funcarg provider_data
    """
    alert_profile = explorer.VMInstanceAlertProfile(
        "Alert profile for %s" % vm_name,
        alerts
    )
    alert_profile.create()
    request.addfinalizer(alert_profile.delete)
    alert_profile.assign_to("The Enterprise")
    action = explorer.Action(
        "Evaluate Alerts for %s" % vm_name,
        "Evaluate Alerts",
        alerts
    )
    action.create()
    request.addfinalizer(action.delete)
    policy = explorer.VMControlPolicy(
        "Evaluate Alerts policy for %s" % vm_name,
        scope="fill_field(VM and Instance : Name, INCLUDES, %s)" % vm_name
    )
    policy.create()
    request.addfinalizer(policy.delete)
    policy_profile = explorer.PolicyProfile(
        "Policy profile for %s" % vm_name, [policy]
    )
    policy_profile.create()
    request.addfinalizer(policy_profile.delete)
    policy.assign_actions_to_event(event, [action])
    prov = provider.Provider(provider_data["name"])
    prov.assign_policy_profiles(policy_profile.description)


def test_alert_vm_turned_on_more_than_twice_in_past_15_minutes(
        test_vm_power_control, provider_crud, provider_data, provider_mgmt, provider_type, request,
        smtp_test):
    if len(test_vm_power_control) == 0:
        pytest.skip("No power control vm specified!")
    test_vm_power_control = test_vm_power_control[0]
    alert = explorer.Alert("VM Power On > 2 in last 15 min")
    setup_for_alerts(request, [alert], "VM Power On", test_vm_power_control, provider_data)

    # Ok, hairy stuff done, now - hammertime!
    provider_mgmt.stop_vm(test_vm_power_control)
    wait_for(lambda: provider_mgmt.is_vm_stopped(test_vm_power_control), num_sec=240)
    for i in range(5):
        provider_mgmt.start_vm(test_vm_power_control)
        wait_for(lambda: provider_mgmt.is_vm_running(test_vm_power_control), num_sec=240)
        provider_mgmt.stop_vm(test_vm_power_control)
        wait_for(lambda: provider_mgmt.is_vm_stopped(test_vm_power_control), num_sec=240)

    wait_for_alert(smtp_test, alert, delay=800)
