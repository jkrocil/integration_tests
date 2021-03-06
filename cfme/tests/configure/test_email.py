from cfme.configure import configuration
from utils.wait import wait_for


def test_send_test_email(smtp_test, random_string):
    """ This test checks whether the mail sent for testing really arrives.

    """
    e_mail = random_string + "@email.test"
    configuration.SMTPSettings.send_test_email(e_mail)
    wait_for(lambda: len(smtp_test.get_emails(to_address=e_mail)) > 0, num_sec=60)
    print smtp_test.get_emails()
