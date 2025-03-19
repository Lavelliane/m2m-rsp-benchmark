"""
Root CA (Certificate Authority) implementation for M2M RSP
Handles certificate issuance and management
"""

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
import datetime
import os

from utils.timing import TimingContext

class RootCA:
    def __init__(self):
        # Generate root CA key pair
        with TimingContext("Root CA Key Generation"):
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
        
        # Generate self-signed certificate
        with TimingContext("Root CA Certificate Generation"):
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, u"San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"M2M RSP Root CA"),
                x509.NameAttribute(NameOID.COMMON_NAME, u"M2M RSP Root CA"),
            ])
            
            self.certificate = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                self.private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.utcnow()
            ).not_valid_after(
                # Root CA certificate is valid for 10 years
                datetime.datetime.utcnow() + datetime.timedelta(days=3650)
            ).add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            ).add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False
                ), critical=True
            ).sign(self.private_key, hashes.SHA256(), default_backend())
        
        with TimingContext("Root CA Initialization"):
            pass  # Timing context for overall initialization
    
    def issue_certificate(self, common_name, public_key, 
                         country="US", state="CA", locality="San Francisco", 
                         organization="M2M RSP Entity"):
        """Issue a certificate for an entity"""
        
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, country),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, state),
            x509.NameAttribute(NameOID.LOCALITY_NAME, locality),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            self.certificate.subject
        ).public_key(
            public_key
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            # Certificates are valid for 1 year
            datetime.datetime.utcnow() + datetime.timedelta(days=365)
        ).add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        ).add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False
            ), critical=True
        ).sign(self.private_key, hashes.SHA256(), default_backend())
        
        return cert
    
    def save_key_and_cert(self, key_path, cert_path):
        """Save the CA key and certificate to disk"""
        with TimingContext("Root CA Key and Certificate Storage"):
            # Ensure directory exists
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            
            # Save private key
            with open(key_path, "wb") as f:
                f.write(self.private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Save certificate
            with open(cert_path, "wb") as f:
                f.write(self.certificate.public_bytes(serialization.Encoding.PEM)) 