from flask import (Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, )
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date, timedelta
import uuid
import qrcode
import base64
from io import BytesIO
import json
from datetime import datetime, timezone
import uuid
import base64
import io
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify, Response
from datetime import datetime, timezone, timedelta
from flask import request, jsonify, session, render_template, abort, redirect, url_for, flash, send_file
now = datetime.now(timezone.utc)


# Import models and forms
from models import (db, Ministry, Hospital, HospitalAdmin, Patient, PatientIdentifier, Doctor, MedicalEncounter,
                     AuditLog, PatientHospital, )
from forms import (LoginForm, HospitalForm, HospitalAdminForm, PatientForm, PatientIdentifierForm, DoctorForm,
                   MedicalEncounterForm, PatientSearchForm, ChangePasswordForm, ProfileUpdateForm,
                   MedicalRecordSearchForm, json_to_contact_info, json_to_address, contact_info_to_form_data,
                   address_to_form_data, specialties_to_form_data, form_data_to_specialties, )


def create_app():
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = "your-secret-key-change-in-production"
    csrf=CSRFProtect(app)
    app.config["SQLALCHEMY_DATABASE_URI"] = (
        "mysql+pymysql://root@localhost:3308/carecode?charset=utf8mb4"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # Initialize extensions
    db.init_app(app)

    # Authentication decorators
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return decorated_function

    def hospital_admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("user_type") != "hospital_admin":
                flash("Hospital admin access required", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    def doctor_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("user_type") != "doctor":
                flash("Doctor access required", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return decorated_function

    # Utility functions
    def log_audit(action, patient_id=None, hospital_id=None, details=None):
        """Log user actions for audit purposes"""
        audit_log = AuditLog(
            acting_user_type=session.get("user_type"),
            acting_user_id=session.get("user_id"),
            patient_id=patient_id,
            hospital_id=hospital_id or session.get("hospital_id"),
            action=action,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", ""),
        )
        db.session.add(audit_log)

    def generate_qr_code(data):
        """Generate QR code and return base64 encoded image"""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        return base64.b64encode(buffer.getvalue()).decode()

    # Routes
    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("index.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if "user_id" in session:
            return redirect(url_for("dashboard"))

        form = LoginForm()
        if form.validate_on_submit():
            username = form.username.data
            password = form.password.data

            # Try hospital admin login
            hospital_admin = HospitalAdmin.query.filter_by(
                username=username, is_active=True
            ).first()
            if hospital_admin and check_password_hash(
                    hospital_admin.password_hash, password
            ):
                session["user_id"] = hospital_admin.id
                session["user_type"] = "hospital_admin"
                session["username"] = hospital_admin.username
                session["hospital_id"] = hospital_admin.hospital_id
                flash(f"Welcome, {hospital_admin.full_name}!", "success")
                return redirect(url_for("dashboard"))

            # Try doctor login
            doctor = Doctor.query.filter_by(license_no=username, is_active=True).first()
            if doctor and check_password_hash(doctor.password_hash, password):
                session["user_id"] = doctor.id
                session["user_type"] = "doctor"
                session["username"] = doctor.license_no
                session["hospital_id"] = doctor.hospital_id
                flash(f"Welcome, Dr. {doctor.full_name}!", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid username or password", "error")

        return render_template("login.html", form=form)

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out", "info")
        return redirect(url_for("index"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user_type = session.get("user_type")
        context = {"user_type": user_type}

        if user_type == "hospital_admin":
            admin = HospitalAdmin.query.get(session["user_id"])
            hospital = Hospital.query.get(session["hospital_id"])
            context.update(
                {
                    "admin": admin,
                    "hospital": hospital,
                    "total_patients": Patient.query.filter_by(
                        created_by_hospital=hospital.id
                    ).count(),
                    "total_doctors": Doctor.query.filter_by(
                        hospital_id=hospital.id
                    ).count(),
                    "recent_encounters": MedicalEncounter.query.filter_by(
                        hospital_id=hospital.id
                    )
                    .order_by(MedicalEncounter.created_at.desc())
                    .limit(5)
                    .all(),
                }
            )

        elif user_type == "doctor":
            doctor = Doctor.query.get(session["user_id"])
            hospital = Hospital.query.get(session["hospital_id"])
            context.update(
                {
                    "doctor": doctor,
                    "hospital": hospital,
                    "today_encounters": MedicalEncounter.query.filter_by(
                        doctor_id=doctor.id, treatment_date=date.today()
                    ).count(),
                    "total_patients_treated": db.session.query(
                        MedicalEncounter.patient_id
                    )
                    .filter_by(doctor_id=doctor.id)
                    .distinct()
                    .count(),
                    "recent_encounters": MedicalEncounter.query.filter_by(
                        doctor_id=doctor.id
                    )
                    .order_by(MedicalEncounter.created_at.desc())
                    .limit(5)
                    .all(),
                }
            )

        return render_template("dashboard.html", **context)

    # Hospital Admin routes
    @app.route("/hospitals")
    @hospital_admin_required
    def hospitals():
        hospital = Hospital.query.get(session["hospital_id"])
        form = HospitalForm()
        return render_template(
            "hospitals/detail.html", hospital=hospital, form=form
        )

    @app.route("/hospitals/<int:hospital_id>/edit", methods=["GET", "POST"])
    @hospital_admin_required
    def edit_hospital(hospital_id):
        # Only allow editing their own hospital
        if hospital_id != session["hospital_id"]:
            abort(403)

        hospital = Hospital.query.get_or_404(hospital_id)
        form = HospitalForm()
        form.hospital_id = hospital_id  # For validation

        if form.validate_on_submit():
            location = json_to_address(
                address_line1=form.address.data,
                city=form.city.data,
                province=form.province.data,
                postal_code=form.postal_code.data,
            )

            contact_info = json_to_contact_info(
                phone_primary=form.contact_phone.data,
                email=form.contact_email.data,
                emergency_contact=form.emergency_contact.data,
            )

            hospital.name = form.name.data
            hospital.code = form.code.data or None
            hospital.location = location
            hospital.contact_info = contact_info

            db.session.commit()

            log_audit(
                "hospital_updated",
                hospital_id=hospital.id,
                details={"hospital_name": hospital.name},
            )
            flash(f'Hospital "{hospital.name}" updated successfully!', "success")
            return redirect(url_for("hospitals"))

        # Pre-populate form
        if request.method == "GET":
            form.name.data = hospital.name
            form.code.data = hospital.code

            if hospital.location:
                location_data = address_to_form_data(hospital.location)
                form.address.data = location_data.get("address_line1", "")
                form.city.data = location_data.get("city", "")
                form.province.data = location_data.get("province", "")
                form.postal_code.data = location_data.get("postal_code", "")

            if hospital.contact_info:
                contact_data = contact_info_to_form_data(hospital.contact_info)
                form.contact_phone.data = contact_data.get("phone_primary", "")
                form.contact_email.data = contact_data.get("email", "")
                form.emergency_contact.data = contact_data.get("emergency_contact", "")

        return render_template("hospitals/edit.html", form=form, hospital=hospital)

    @app.route("/patients")
    @login_required
    def patients():
        search_form = PatientSearchForm()
        query = Patient.query

        # Hospital admins and doctors can only see their hospital's patients
        hospital_id = session["hospital_id"]
        current_hospital = Hospital.query.get(hospital_id)
        query = query.filter_by(created_by_hospital=hospital_id)

        # Apply search filters
        if search_form.validate() and search_form.search_term.data:
            search_term = f"%{search_form.search_term.data}%"
            if search_form.search_type.data == "name":
                query = query.filter(Patient.full_name.ilike(search_term))
            elif search_form.search_type.data == "email":
                query = query.filter(Patient.email.ilike(search_term))
            elif search_form.search_type.data == "phone":
                # Search in JSON contact_info field
                query = query.filter(
                    db.or_(
                        Patient.contact_info['phone_primary'].astext.ilike(search_term),
                        Patient.contact_info['phone_secondary'].astext.ilike(search_term)
                    )
                )
            elif search_form.search_type.data == "identifier":
                query = query.join(PatientIdentifier).filter(
                    PatientIdentifier.id_value.ilike(search_term)
                )
            else:  # all fields
                query = query.filter(
                    db.or_(
                        Patient.full_name.ilike(search_term),
                        Patient.email.ilike(search_term),
                        Patient.guardian_number.ilike(search_term),
                        Patient.contact_info['phone_primary'].astext.ilike(search_term)
                    )
                )

        # Get patients with proper ordering
        patients = query.order_by(Patient.created_at.desc()).limit(50).all()

        return render_template(
            "patients/list.html",
            patients=patients,
            search_form=search_form,
            current_hospital=current_hospital
        )

    # Add this route to your app.py for QR scanning functionality

    @app.route("/scan-qr")
    @doctor_required
    def qr_scanner():
        """QR Scanner page for doctors"""
        return render_template("qr_scanner.html")

    import qrcode
    import io
    import base64
    from flask import request, url_for, render_template

    # New public route for QR code access
    @app.route('/patient/qr/<token>')
    def patient_qr_view(token):
        """Public route accessible via QR code - no login required"""
        patient = Patient.query.filter_by(qr_token=token, is_active=True).first()

        if not patient:
            flash('Invalid or expired patient QR code.', 'error')
            return redirect(url_for('index'))

        # Log the QR access for audit purposes
        # You might want to add audit logging here

        return render_template('patient_qr_view.html', patient=patient)



    # Helper function for templates
    @app.context_processor
    def utility_processor():
        def get_patient_qr_code(patient):
            if patient.qr_code_image:
                return patient.qr_code_image
            # Generate on-demand if not stored
            base_url = request.url_root.rstrip('/')
            return patient.generate_qr_code(base_url)

        return dict(get_patient_qr_code=get_patient_qr_code)

    @app.route("/patients/<int:patient_id>")
    @login_required
    def patient_detail(patient_id):
        patient = Patient.query.get_or_404(patient_id)

        # Remove this hospital restriction for QR code access
        # if patient.created_by_hospital != session["hospital_id"]:
        #     abort(403)

        encounters = (
            MedicalEncounter.query.filter_by(patient_id=patient_id)
            .order_by(MedicalEncounter.treatment_date.desc())
            .all()
        )
        identifiers = PatientIdentifier.query.filter_by(patient_id=patient_id).all()

        log_audit("patient_viewed", patient_id=patient_id)

        return render_template(
            "patients/detail.html",
            patient=patient,
            encounters=encounters,
            identifiers=identifiers,
        )

    @app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_patient(patient_id):
        patient = Patient.query.get_or_404(patient_id)

        # Check permissions
        if patient.created_by_hospital != session["hospital_id"]:
            abort(403)

        form = PatientForm()
        if form.validate_on_submit():
            address = json_to_address(
                address_line1=form.address_line1.data,
                address_line2=form.address_line2.data,
                city=form.city.data,
                province=form.province.data,
                postal_code=form.postal_code.data,
                country=form.country.data,
            )

            contact_info = json_to_contact_info(
                phone_primary=form.phone_primary.data,
                phone_secondary=form.phone_secondary.data,
                email=form.email.data,
            )

            patient.full_name = form.full_name.data
            patient.date_of_birth = form.date_of_birth.data
            patient.gender = form.gender.data or None
            patient.address = address
            patient.contact_info = contact_info
            patient.email = form.email.data
            patient.blood_type = form.blood_type.data or None
            patient.guardian_number = form.guardian_number.data
            patient.updated_at = datetime.now(timezone.utc)

            db.session.commit()

            log_audit(
                "patient_updated",
                patient_id=patient.id,
                details={"patient_name": patient.full_name},
            )
            flash(f'Patient "{patient.full_name}" updated successfully!', "success")
            return redirect(url_for("patient_detail", patient_id=patient.id))

        # Pre-populate form
        if request.method == "GET":
            form.full_name.data = patient.full_name
            form.date_of_birth.data = patient.date_of_birth
            form.gender.data = patient.gender
            form.email.data = patient.email
            form.blood_type.data = patient.blood_type
            form.guardian_number.data = patient.guardian_number

            if patient.address:
                address_data = address_to_form_data(patient.address)
                form.address_line1.data = address_data.get("address_line1", "")
                form.address_line2.data = address_data.get("address_line2", "")
                form.city.data = address_data.get("city", "")
                form.province.data = address_data.get("province", "")
                form.postal_code.data = address_data.get("postal_code", "")
                form.country.data = address_data.get("country", "Sri Lanka")

            if patient.contact_info:
                contact_data = contact_info_to_form_data(patient.contact_info)
                form.phone_primary.data = contact_data.get("phone_primary", "")
                form.phone_secondary.data = contact_data.get("phone_secondary", "")

        return render_template("patients/edit.html", form=form, patient=patient)

    @app.route("/patients/<int:patient_id>/identifiers/add", methods=["GET", "POST"])
    @hospital_admin_required
    def add_patient_identifier(patient_id):
        patient = Patient.query.get_or_404(patient_id)
        form = PatientIdentifierForm()

        if form.validate_on_submit():
            # Check for duplicate identifier
            existing = PatientIdentifier.query.filter_by(
                id_type=form.id_type.data, id_value=form.id_value.data
            ).first()

            if existing:
                flash("This identifier already exists for another patient", "error")
                return render_template(
                    "patients/add_identifier.html", form=form, patient=patient
                )

            identifier = PatientIdentifier(
                patient_id=patient_id,
                id_type=form.id_type.data,
                id_value=form.id_value.data,
                issued_country=form.issued_country.data,
            )

            db.session.add(identifier)
            db.session.commit()

            log_audit(
                "patient_identifier_added",
                patient_id=patient_id,
                details={
                    "id_type": identifier.id_type,
                    "id_value": identifier.id_value,
                },
            )
            flash("Patient identifier added successfully!", "success")
            return redirect(url_for("patient_detail", patient_id=patient_id))

        return render_template(
            "patients/add_identifier.html", form=form, patient=patient
        )

    @app.route("/doctors")
    @hospital_admin_required
    def doctors():
        # Hospital admins can only see doctors from their hospital
        doctors = Doctor.query.filter_by(hospital_id=session["hospital_id"]).order_by(Doctor.full_name).all()
        return render_template("doctors/list.html", doctors=doctors)

    @app.route("/doctors/add", methods=["GET", "POST"])
    @hospital_admin_required
    def add_doctor():
        form = DoctorForm()
        if form.validate_on_submit():
            contact_info = json_to_contact_info(
                phone_primary=form.phone_primary.data,
                phone_secondary=form.phone_secondary.data,
                email=form.email.data,
            )

            specialties = form_data_to_specialties(
                form.specialty_1.data, form.specialty_2.data, form.specialty_3.data
            )

            doctor = Doctor(
                hospital_id=session["hospital_id"],
                license_no=form.license_no.data,
                password_hash=generate_password_hash(form.password.data),
                full_name=form.full_name.data,
                nic=form.nic.data,
                contact_info=contact_info,
                email=form.email.data,
                specialties=specialties,
                is_active=form.is_active.data,
            )

            db.session.add(doctor)
            db.session.commit()

            log_audit(
                "doctor_created",
                hospital_id=session["hospital_id"],
                details={
                    "doctor_name": doctor.full_name,
                    "license_no": doctor.license_no,
                },
            )
            flash(f'Doctor "{doctor.full_name}" created successfully!', "success")
            return redirect(url_for("doctors"))

        return render_template("doctors/add.html", form=form)

    @app.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
    @hospital_admin_required
    def edit_doctor(doctor_id):
        doctor = Doctor.query.get_or_404(doctor_id)

        # Check permissions - only allow editing doctors from their hospital
        if doctor.hospital_id != session["hospital_id"]:
            abort(403)

        form = DoctorForm(doctor_id=doctor_id)
        if form.validate_on_submit():
            contact_info = json_to_contact_info(
                phone_primary=form.phone_primary.data,
                phone_secondary=form.phone_secondary.data,
                email=form.email.data,
            )

            specialties = form_data_to_specialties(
                form.specialty_1.data, form.specialty_2.data, form.specialty_3.data
            )

            doctor.license_no = form.license_no.data
            if form.password.data:  # Only update password if provided
                doctor.password_hash = generate_password_hash(form.password.data)
            doctor.full_name = form.full_name.data
            doctor.nic = form.nic.data
            doctor.contact_info = contact_info
            doctor.email = form.email.data
            doctor.specialties = specialties
            doctor.is_active = form.is_active.data

            db.session.commit()

            log_audit(
                "doctor_updated",
                hospital_id=doctor.hospital_id,
                details={
                    "doctor_name": doctor.full_name,
                    "license_no": doctor.license_no,
                },
            )
            flash(f'Doctor "{doctor.full_name}" updated successfully!', "success")
            return redirect(url_for("doctors"))

        # Pre-populate form
        if request.method == "GET":
            form.license_no.data = doctor.license_no
            form.full_name.data = doctor.full_name
            form.nic.data = doctor.nic
            form.email.data = doctor.email
            form.is_active.data = doctor.is_active

            if doctor.contact_info:
                contact_data = contact_info_to_form_data(doctor.contact_info)
                form.phone_primary.data = contact_data.get("phone_primary", "")
                form.phone_secondary.data = contact_data.get("phone_secondary", "")

            if doctor.specialties:
                specialty_data = specialties_to_form_data(doctor.specialties)
                form.specialty_1.data = specialty_data.get("specialty_1", "")
                form.specialty_2.data = specialty_data.get("specialty_2", "")
                form.specialty_3.data = specialty_data.get("specialty_3", "")

        return render_template("doctors/edit.html", form=form, doctor=doctor)

    # Doctor routes
    @app.route("/encounters")
    @doctor_required
    def encounters():
        doctor = Doctor.query.get(session["user_id"])
        encounters = (
            MedicalEncounter.query.filter_by(doctor_id=doctor.id)
            .order_by(MedicalEncounter.treatment_date.desc())
            .all()
        )

        # Get patient from query parameter if provided
        patient_id = request.args.get('patient_id')
        patient = None
        if patient_id:
            patient = Patient.query.get_or_404(patient_id)
            # Verify doctor can access this patient
            if patient.created_by_hospital != session["hospital_id"]:
                abort(403)

        return render_template(
            "encounters/list.html",
            encounters=encounters,
            doctor=doctor,
            patient=patient
        )

    @app.route("/encounters/add/<int:patient_id>", methods=["GET", "POST"])
    @doctor_required
    def add_encounter(patient_id):
        patient = Patient.query.get_or_404(patient_id)
        doctor = Doctor.query.get(session["user_id"])

        # Verify patient can be treated at this hospital
        if patient.created_by_hospital != session["hospital_id"]:
            # Check if patient has been seen at this hospital
            patient_hospital = PatientHospital.query.filter_by(
                patient_id=patient_id, hospital_id=session["hospital_id"]
            ).first()

            if not patient_hospital:
                # Create new patient-hospital relationship
                patient_hospital = PatientHospital(
                    patient_id=patient_id,
                    hospital_id=session["hospital_id"],
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                )
                db.session.add(patient_hospital)
            else:
                patient_hospital.last_seen = datetime.now(timezone.utc)

        form = MedicalEncounterForm()
        form.patient_id.data = patient_id

        if form.validate_on_submit():
            medicines = form.get_medicines_json()

            encounter = MedicalEncounter(
                receipt_number=form.receipt_number.data,
                patient_id=patient_id,
                doctor_id=doctor.id,
                hospital_id=session["hospital_id"],
                diagnosis_text=form.diagnosis_text.data,
                diagnosis_code=form.diagnosis_code.data,
                medicines=medicines,
                suggestions=form.suggestions.data,
                treatment_date=form.treatment_date.data,
            )

            db.session.add(encounter)
            db.session.commit()

            log_audit(
                "encounter_created",
                patient_id=patient_id,
                details={
                    "doctor_name": doctor.full_name,
                    "diagnosis": form.diagnosis_text.data[:100],
                },
            )
            flash("Medical encounter recorded successfully!", "success")
            return redirect(url_for("patient_detail", patient_id=patient_id))

        return render_template(
            "encounters/add.html", form=form, patient=patient, doctor=doctor
        )

    @app.route("/encounters/<int:encounter_id>/edit", methods=["GET", "POST"])
    @doctor_required
    def edit_encounter(encounter_id):
        encounter = MedicalEncounter.query.get_or_404(encounter_id)

        # Only the doctor who created the encounter can edit it
        if encounter.doctor_id != session["user_id"]:
            abort(403)

        form = MedicalEncounterForm()
        if form.validate_on_submit():
            medicines = form.get_medicines_json()

            encounter.receipt_number = form.receipt_number.data
            encounter.diagnosis_text = form.diagnosis_text.data
            encounter.diagnosis_code = form.diagnosis_code.data
            encounter.medicines = medicines
            encounter.suggestions = form.suggestions.data
            encounter.treatment_date = form.treatment_date.data

            db.session.commit()

            log_audit(
                "encounter_updated",
                patient_id=encounter.patient_id,
                details={
                    "encounter_id": encounter.id,
                    "diagnosis": form.diagnosis_text.data[:100],
                },
            )
            flash("Medical encounter updated successfully!", "success")
            return redirect(url_for("patient_detail", patient_id=encounter.patient_id))

        # Pre-populate form
        if request.method == "GET":
            form.patient_id.data = encounter.patient_id
            form.receipt_number.data = encounter.receipt_number
            form.diagnosis_text.data = encounter.diagnosis_text
            form.diagnosis_code.data = encounter.diagnosis_code
            form.suggestions.data = encounter.suggestions
            form.treatment_date.data = encounter.treatment_date

            if encounter.medicines:
                form.populate_medicine_fields(encounter.medicines)

        return render_template("encounters/edit.html", form=form, encounter=encounter)




    @app.route("/search/patients")
    @login_required
    def search_patients_api():
        term = request.args.get("term", "").strip()
        if len(term) < 2:
            return jsonify([])

        # Hospital admins and doctors can only search their hospital's patients
        query = Patient.query.filter_by(created_by_hospital=session["hospital_id"])

        # Search by name or identifier
        search_term = f"%{term}%"
        patients = (
            query.filter(
                db.or_(
                    Patient.full_name.ilike(search_term),
                    Patient.email.ilike(search_term),
                )
            )
            .limit(10)
            .all()
        )

        # Also search by identifiers
        identifier_patients = (
            query.join(PatientIdentifier)
            .filter(PatientIdentifier.id_value.ilike(search_term))
            .limit(5)
            .all()
        )

        # Combine and deduplicate
        all_patients = {p.id: p for p in patients + identifier_patients}

        results = []
        for patient in all_patients.values():
            results.append(
                {
                    "id": patient.id,
                    "name": patient.full_name,
                    "email": patient.email or "",
                    "dob": (
                        patient.date_of_birth.strftime("%Y-%m-%d")
                        if patient.date_of_birth
                        else ""
                    ),
                    "blood_type": patient.blood_type or "",
                }
            )

        return jsonify(results)

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        user_type = session.get("user_type")
        form = ProfileUpdateForm()

        if user_type == "doctor":
            user = Doctor.query.get(session["user_id"])
        elif user_type == "hospital_admin":
            user = HospitalAdmin.query.get(session["user_id"])
        else:
            flash("Profile editing not available for your user type", "error")
            return redirect(url_for("dashboard"))

        if form.validate_on_submit():
            user.full_name = form.full_name.data
            user.email = form.email.data

            if hasattr(user, "contact_info"):
                contact_info = json_to_contact_info(
                    phone_primary=form.phone_primary.data,
                    phone_secondary=form.phone_secondary.data,
                    email=form.email.data,
                )
                user.contact_info = contact_info

            db.session.commit()

            log_audit(
                "profile_updated",
                details={"user_type": user_type, "user_name": user.full_name},
            )
            flash("Profile updated successfully!", "success")
            return redirect(url_for("profile"))

        # Pre-populate form
        if request.method == "GET":
            form.full_name.data = user.full_name
            form.email.data = user.email

            if hasattr(user, "contact_info") and user.contact_info:
                contact_data = contact_info_to_form_data(user.contact_info)
                form.phone_primary.data = contact_data.get("phone_primary", "")
                form.phone_secondary.data = contact_data.get("phone_secondary", "")

        return render_template(
            "profile.html", form=form, user=user, user_type=user_type
        )

    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        form = ChangePasswordForm()
        user_type = session.get("user_type")

        if form.validate_on_submit():
            # Get current user
            if user_type == "hospital_admin":
                user = HospitalAdmin.query.get(session["user_id"])
            elif user_type == "doctor":
                user = Doctor.query.get(session["user_id"])
            else:
                flash("Password change not available for your user type", "error")
                return redirect(url_for("dashboard"))

            # Verify current password
            if not check_password_hash(user.password_hash, form.current_password.data):
                flash("Current password is incorrect", "error")
                return render_template("change_password.html", form=form)

            # Update password
            user.password_hash = generate_password_hash(form.new_password.data)
            db.session.commit()

            log_audit("password_changed", details={"user_type": user_type})
            flash("Password changed successfully!", "success")
            return redirect(url_for("profile"))

        return render_template("change_password.html", form=form)

    @app.route("/medical-records")
    @login_required
    def medical_records():
        search_form = MedicalRecordSearchForm()
        query = MedicalEncounter.query

        # Apply hospital restrictions
        if session.get("user_type") == "doctor":
            query = query.filter_by(doctor_id=session["user_id"])
        elif session.get("user_type") == "hospital_admin":
            query = query.filter_by(hospital_id=session["hospital_id"])

        # Apply search filters if provided
        if request.args.get("search"):
            if search_form.patient_name.data:
                query = query.join(Patient).filter(
                    Patient.full_name.ilike(f"%{search_form.patient_name.data}%")
                )
            if search_form.doctor_name.data:
                query = query.join(Doctor).filter(
                    Doctor.full_name.ilike(f"%{search_form.doctor_name.data}%")
                )
            if search_form.diagnosis_keyword.data:
                query = query.filter(
                    MedicalEncounter.diagnosis_text.ilike(
                        f"%{search_form.diagnosis_keyword.data}%"
                    )
                )
            if search_form.date_from.data:
                query = query.filter(
                    MedicalEncounter.treatment_date >= search_form.date_from.data
                )
            if search_form.date_to.data:
                query = query.filter(
                    MedicalEncounter.treatment_date <= search_form.date_to.data
                )

        encounters = (
            query.order_by(MedicalEncounter.treatment_date.desc()).limit(100).all()
        )
        return render_template(
            "medical_records.html", encounters=encounters, search_form=search_form
        )

    @app.route("/reports")
    @login_required
    def reports():
        user_type = session.get("user_type")

        if user_type == "hospital_admin":
            hospital = Hospital.query.get(session["hospital_id"])

            total_patients = Patient.query.filter_by(
                created_by_hospital=hospital.id
            ).count()
            total_doctors = Doctor.query.filter_by(hospital_id=hospital.id).count()
            total_encounters = MedicalEncounter.query.filter_by(
                hospital_id=hospital.id
            ).count()

            context = {
                "hospital": hospital,
                "total_patients": total_patients,
                "total_doctors": total_doctors,
                "total_encounters": total_encounters,
            }

        elif user_type == "doctor":
            doctor = Doctor.query.get(session["user_id"])
            hospital = Hospital.query.get(session["hospital_id"])

            total_encounters = MedicalEncounter.query.filter_by(
                doctor_id=doctor.id
            ).count()
            total_patients = (
                db.session.query(MedicalEncounter.patient_id)
                .filter_by(doctor_id=doctor.id)
                .distinct()
                .count()
            )

            context = {
                "doctor": doctor,
                "hospital": hospital,
                "total_encounters": total_encounters,
                "total_patients": total_patients,
            }

        return render_template("reports.html", **context, user_type=user_type)

    @app.route("/audit-logs")
    @hospital_admin_required
    def audit_logs():
        # Only hospital admins can view audit logs for their hospital
        query = AuditLog.query.filter_by(hospital_id=session["hospital_id"])
        logs = query.order_by(AuditLog.created_at.desc()).limit(100).all()
        return render_template("audit_logs.html", logs=logs)

    @app.route("/api/patient/<patient_id>/summary")
    @login_required
    def patient_summary_api(patient_id):
        patient = Patient.query.get_or_404(patient_id)

        # Check access permissions
        if not can_access_patient(patient.id):
            abort(403)

        recent_encounters = (
            MedicalEncounter.query.filter_by(patient_id=patient_id)
            .order_by(MedicalEncounter.treatment_date.desc())
            .limit(5)
            .all()
        )

        encounters_data = []
        for encounter in recent_encounters:
            encounters_data.append(
                {
                    "id": encounter.id,
                    "date": encounter.treatment_date.strftime("%Y-%m-%d"),
                    "doctor": (
                        encounter.doctor.full_name if encounter.doctor else "Unknown"
                    ),
                    "diagnosis": encounter.diagnosis_text,
                    "hospital": encounter.hospital.name,
                }
            )

        return jsonify(
            {
                "patient": {
                    "id": patient.id,
                    "name": patient.full_name,
                    "dob": (
                        patient.date_of_birth.strftime("%Y-%m-%d")
                        if patient.date_of_birth
                        else None
                    ),
                    "blood_type": patient.blood_type,
                    "gender": patient.gender,
                },
                "recent_encounters": encounters_data,
                "total_encounters": MedicalEncounter.query.filter_by(
                    patient_id=patient_id
                ).count(),
            }
        )



    def can_access_patient(patient_id):
        """Check if current user can access patient data"""
        patient = Patient.query.get(patient_id)
        if not patient:
            return False

        # Hospital admins and doctors can only access patients from their hospital
        if patient.created_by_hospital == session["hospital_id"]:
            return True

        # Check if patient has been seen at this hospital
        return (
                PatientHospital.query.filter_by(
                    patient_id=patient_id, hospital_id=session["hospital_id"]
                ).first()
                is not None
        )

    # Add this function after your existing generate_qr_code function in app.py


    # Modify your add_patient route to include auto QR generation
    @app.route("/patients/add", methods=["GET", "POST"])
    @hospital_admin_required
    def add_patient():
        hospital_id = session.get("hospital_id")
        hospital = Hospital.query.filter_by(id=hospital_id, is_active=True).first()

        if not hospital:
            flash("Invalid hospital selected.", "error")
            return redirect(url_for("patients"))

        form = PatientForm()

        if form.validate_on_submit():
            try:
                # Clean the form data
                cleaned_data = form.clean_data()

                # Convert form data to JSON objects
                address = json_to_address(
                    address_line1=cleaned_data.get('address_line1', form.address_line1.data),
                    address_line2=cleaned_data.get('address_line2', form.address_line2.data),
                    city=cleaned_data.get('city', form.city.data),
                    province=cleaned_data.get('province', form.province.data),
                    postal_code=cleaned_data.get('postal_code', form.postal_code.data),
                    country=cleaned_data.get('country', form.country.data),
                )

                contact_info = json_to_contact_info(
                    phone_primary=cleaned_data.get('phone_primary', form.phone_primary.data),
                    phone_secondary=cleaned_data.get('phone_secondary', form.phone_secondary.data),
                    email=cleaned_data.get('email', form.email.data),
                )

                # Create Patient instance
                patient = Patient(
                    full_name=cleaned_data.get('full_name', form.full_name.data.strip()),
                    date_of_birth=form.date_of_birth.data,
                    gender=form.gender.data if form.gender.data else None,
                    address=address,
                    contact_info=contact_info,
                    email=cleaned_data.get('email', form.email.data.strip() if form.email.data else None),
                    blood_type=form.blood_type.data if form.blood_type.data else None,
                    guardian_number=cleaned_data.get('guardian_number',
                                                     form.guardian_number.data.strip() if form.guardian_number.data else None),
                    created_by_hospital=hospital_id,
                )

                db.session.add(patient)
                db.session.flush()  # Flush to get patient.id without committing

                # Link patient to hospital
                patient_hospital = PatientHospital(
                    patient_id=patient.id,
                    hospital_id=hospital_id,
                    first_seen=datetime.now(timezone.utc),
                    last_seen=datetime.now(timezone.utc),
                )
                db.session.add(patient_hospital)

                # AUTO-GENERATE QR TOKEN FOR THE NEW PATIENT

                # Commit all operations together
                db.session.commit()

                # Audit log
                log_audit(
                    "patient_created",
                    patient_id=patient.id,
                    details={"patient_name": patient.full_name, "hospital_name": hospital.name,
                             },
                )

                flash(f'Patient "{patient.full_name}" created successfully at {hospital.name}!', "success")


                return redirect(url_for("patient_detail", patient_id=patient.id))

            except Exception as e:
                db.session.rollback()
                app.logger.error(f"Error creating patient: {str(e)}")
                flash(f"Error creating patient: {str(e)}", "error")
                return render_template("patients/add.html", form=form, hospital=hospital)

        else:
            # Log form validation errors for debugging
            if form.errors:
                app.logger.warning(f"Form validation errors: {form.errors}")
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f"{getattr(form, field).label.text}: {error}", "error")

        # Render form if GET request or validation fails
        return render_template("patients/add.html", form=form, hospital=hospital)

    # Add a new route for QR code download
    @app.route("/api/validate-qr", methods=["POST"])
    @doctor_required
    def validate_qr_token():
        """Simple QR validation using Patient.qr_token"""
        try:
            data = request.get_json()
            qr_url = data.get('qr_url', '').strip()

            if not qr_url:
                return jsonify({"success": False, "error": "QR URL is required"})

            # Extract token from URL
            if '/patient/qr/' in qr_url:
                token = qr_url.split('/patient/qr/')[-1]
            else:
                return jsonify({"success": False, "error": "Invalid QR code format"})

            # Find patient by QR token
            patient = Patient.query.filter_by(qr_token=token, is_active=True).first()

            if not patient:
                return jsonify({"success": False, "error": "Invalid QR code"})

            # Log the QR scan access
            log_audit(
                "qr_scanned_by_doctor",
                patient_id=patient.id,
                details={
                    "doctor_id": session["user_id"],
                    "hospital_id": session["hospital_id"]
                }
            )

            return jsonify({
                "success": True,
                "patient_id": patient.id,
                "patient_name": patient.full_name,
                "redirect_url": url_for('patient_detail', patient_id=patient.id)
            })

        except Exception as e:
            app.logger.error(f"Error validating QR token: {str(e)}")
            return jsonify({"success": False, "error": "Server error occurred"})

    @app.route("/patients/<int:patient_id>/qr-download")
    @login_required
    def download_patient_qr(patient_id):
        patient = Patient.query.get_or_404(patient_id)

        if patient.created_by_hospital != session["hospital_id"]:
            abort(403)

        try:
            # Generate QR code for this patient
            qr_url = f"{request.url_root}patient/qr/{patient.qr_token}"
            qr_image_data = generate_qr_code(qr_url)

            # Convert base64 to bytes for download
            image_bytes = base64.b64decode(qr_image_data)

            log_audit("qr_code_downloaded", patient_id=patient_id)

            return Response(
                image_bytes,
                headers={
                    'Content-Type': 'image/png',
                    'Content-Disposition': f'attachment; filename="patient_{patient.full_name.replace(" ", "_")}_qr.png"'
                }
            )

        except Exception as e:
            flash("Error downloading QR code", "error")
            return redirect(url_for("patient_detail", patient_id=patient_id))

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    # Context processors
    @app.context_processor
    def inject_user():
        return dict(
            current_user_type=session.get("user_type"),
            current_user_id=session.get("user_id"),
            current_username=session.get("username"),
            current_hospital_id=session.get("hospital_id"),
            now=datetime.now()
        )

    @app.template_filter("datetime")
    def datetime_filter(value, format="%Y-%m-%d %H:%M"):
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("date")
    def date_filter(value, format="%Y-%m-%d"):
        if value is None:
            return ""
        return value.strftime(format)

    @app.template_filter("json_pretty")
    def json_pretty_filter(value):
        if value is None:
            return ""
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except:
            return str(value)

    # CLI Commands
    @app.cli.command()
    def init_db():
       
        db.create_all()
        print("Database initialized!!")

    @app.cli.command()
    def create_sample_data():
        """Create sample data for testing."""
        # Create sample hospital (assuming it exists or needs to be created manually)
        hospital = Hospital.query.first()
        if not hospital:
            # Create a default hospital for testing
            hospital = Hospital(
                ministry_id=1,  # Assuming ministry with ID 1 exists
                name="Sample General Hospital",
                code="SGH001",
                location={"city": "Colombo", "province": "Western"},
                contact_info={"phone": "+94112691111", "emergency": "+94112691999"},
            )
            db.session.add(hospital)
            db.session.flush()

        # Create sample hospital admin
        admin = HospitalAdmin(
            hospital_id=hospital.id,
            username="admin",
            password_hash=generate_password_hash("password123"),
            full_name="Hospital Administrator",
            email="admin@hospital.com",
        )
        db.session.add(admin)

        # Create sample doctor
        doctor = Doctor(
            hospital_id=hospital.id,
            license_no="DOC001",
            password_hash=generate_password_hash("password123"),
            full_name="Dr. Sample Doctor",
            email="doctor@hospital.com",
            specialties=["General Medicine"],
            contact_info={"phone": "+94771234567"},
        )
        db.session.add(doctor)

        # Create sample patient
        patient = Patient(
            full_name="Sample Patient",
            date_of_birth=date(1990, 1, 1),
            gender="male",
            address={
                "line1": "123 Sample Street",
                "city": "Colombo",
                "province": "Western",
            },
            contact_info={"phone_primary": "+94771111111"},
            email="patient@example.com",
            blood_type="O+",
            created_by_hospital=hospital.id,
        )
        db.session.add(patient)
        db.session.flush()

        # Create patient identifier
        identifier = PatientIdentifier(
            patient_id=patient.id,
            id_type="nic",
            id_value="901234567V",
            issued_country="Sri Lanka",
        )
        db.session.add(identifier)

        # Create patient-hospital relationship
        patient_hospital = PatientHospital(
            patient_id=patient.id,
            hospital_id=hospital.id,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        db.session.add(patient_hospital)

        db.session.commit()
        print("Sample data created!")
        print("Hospital admin: admin / password123")
        print("Doctor: DOC001 / password123")

    # Add this route to your app.py file


    return app



# Create the application instance
app = create_app()

if __name__ == "__main__":

    app.run(debug=True, host="0.0.0.0", port=5000)
