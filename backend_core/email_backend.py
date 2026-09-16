import ssl
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.utils.functional import cached_property

class UnverifiedEmailBackend(SMTPEmailBackend):
    """
    A custom email backend that bypasses SSL certificate verification.
    This is useful for SMTP servers like Godaddy where local SSL certificates 
    might not verify properly, causing [SSL: CERTIFICATE_VERIFY_FAILED] errors.
    """
    @cached_property
    def ssl_context(self):
        return ssl._create_unverified_context()
