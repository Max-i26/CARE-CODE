from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import uuid

db = SQLAlchemy()


# ========================
# Ministries
# ========================
class Ministry(db.Model):
    __tablename__ = 'ministries'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    admin_username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    contact_info = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



# ========================
# Hospitals
# ========================
class Hospital(db.Model):
    __tablename__ = 'hospitals'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    ministry_id = db.Column(db.Integer, db.ForeignKey('ministries.id'), nullable=False)
    code = db.Column(db.String(50), unique=True)
    address = db.Column(db.JSON)  # store hospital address as JSON
    contact_info = db.Column(db.JSON)  # store contact info as JSON
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ministry = db.relationship('Ministry', backref=db.backref('hospitals', lazy=True))
    admins = db.relationship('HospitalAdmin', backref='hospital', lazy=True)
    doctors = db.relationship('Doctor', backref='hospital_relation', lazy=True)
    patients = db.relationship(
        'Patient',
        backref='hospital_relation',
        lazy=True,
        overlaps="created_patients,hospital"
    )
    encounters = db.relationship('MedicalEncounter', backref='hospital', lazy=True)


# ========================
# Patients
# ========================
# ========================
# Patients
# ========================
class Patient(db.Model):
    __tablename__ = 'patients'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    full_name = db.Column(db.String(255), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20), nullable=True)
    address = db.Column(db.JSON)
    contact_info = db.Column(db.JSON)
    email = db.Column(db.String(255), nullable=True)
    blood_type = db.Column(db.String(10), nullable=True)
    guardian_number = db.Column(db.String(50), nullable=True)
    created_by_hospital = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # QR Code fields (stored directly in Patient table)
    qr_token = db.Column(db.String(36), unique=True, nullable=True)
    qr_code_image = db.Column(db.Text, nullable=True)  # Store base64 QR image

    # Relationships
    hospital = db.relationship(
        'Hospital',
        backref=db.backref('created_patients', lazy=True, overlaps="hospital_relation,patients"),
        overlaps="hospital_relation,patients"
    )
    identifiers = db.relationship('PatientIdentifier', backref='patient', lazy=True)
    encounters = db.relationship('MedicalEncounter', backref='patient', lazy=True)
    patient_hospitals = db.relationship('PatientHospital', backref='patient', lazy=True)
    # REMOVED: qr_tokens = db.relationship('QRToken', backref='patient', lazy=True)

    def __init__(self, **kwargs):
        super(Patient, self).__init__(**kwargs)
        if not self.qr_token:
            self.qr_token = str(uuid.uuid4())

    def get_qr_url(self, base_url):
        """Generate the full URL for QR code access"""
        return f"{base_url}/patient/qr/{self.qr_token}"

    def generate_qr_code(self, base_url):
        """Generate QR code image as base64 string"""
        import qrcode
        import io
        import base64

        qr_url = self.get_qr_url(base_url)
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()

        return f"data:image/png;base64,{img_str}"



# ========================
# Hospital Admins
# ========================
class HospitalAdmin(db.Model):
    __tablename__ = 'hospital_admins'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    contact_info = db.Column(db.JSON)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)





# ========================
# Patient Identifiers
# ========================
class PatientIdentifier(db.Model):
    __tablename__ = 'patient_identifiers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    id_type = db.Column(db.String(50), nullable=False)  # matches database column name
    id_value = db.Column(db.String(100), nullable=False)  # matches database column name
    issued_country = db.Column(db.String(100), default='Sri Lanka')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # No explicit relationship definition needed here since it's defined in Patient model


# ========================
# Doctors
# ========================
class Doctor(db.Model):
    __tablename__ = 'doctors'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=False)
    license_no = db.Column(db.String(100), unique=True, nullable=False)  # matches database
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    nic = db.Column(db.String(20), nullable=True)
    contact_info = db.Column(db.JSON)
    email = db.Column(db.String(255), nullable=True)
    specialties = db.Column(db.JSON)  # matches database (plural)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    encounters = db.relationship('MedicalEncounter', backref='doctor', lazy=True)


# ========================
# Medical Encounters
# ========================
class MedicalEncounter(db.Model):
    __tablename__ = 'medical_encounters'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    receipt_number = db.Column(db.String(100), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=False)
    diagnosis_text = db.Column(db.Text)  # matches database column name
    diagnosis_code = db.Column(db.String(20), nullable=True)
    medicines = db.Column(db.JSON)
    suggestions = db.Column(db.Text)
    treatment_date = db.Column(db.Date, nullable=False)  # matches database column name
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # No explicit relationship definitions needed here since they're defined in the parent models



# ========================
# Audit Logs
# ========================
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    acting_user_type = db.Column(db.String(50), nullable=True)  # matches database column name
    acting_user_id = db.Column(db.Integer, nullable=True)  # matches database column name
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)  # matches database length
    details = db.Column(db.JSON)  # matches database column name
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships for foreign keys
    patient = db.relationship('Patient', backref=db.backref('audit_logs', lazy=True))
    hospital = db.relationship('Hospital', backref=db.backref('audit_logs', lazy=True))


# ========================
# Patient ↔ Hospital Relationship
# ========================
class PatientHospital(db.Model):
    __tablename__ = 'patient_hospitals'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospitals.id'), nullable=False)
    first_seen = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    # No explicit relationship definitions needed here since they're defined in Patient model