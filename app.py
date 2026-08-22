"""
MARG — Smart Road Safety Awareness
Flask + SQLAlchemy + MySQL backend

Run locally:
    pip install -r requirements.txt
    python app.py

Every endpoint except /signup and /login expects:
    Authorization: Bearer <token>
"""

import os
import math
import json
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
import pymysql
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

pymysql.install_as_MySQLdb()

# ---------------------------------------------------------------- app setup

app = Flask(__name__)
CORS(app)

# Reads from Railway environment variable
db_url = os.environ.get('DATABASE_URL', '')
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'marg_secret_2026')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ------------------------------------------------------- firebase (optional)
# The server can run without Firebase; SOS just won't push. That keeps local
# development simple before the service account key is in place.

FIREBASE_READY = False
try:
    import firebase_admin
    from firebase_admin import credentials, messaging

    cred_json = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_json:
        cred = credentials.Certificate(json.loads(cred_json))
    elif os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
    else:
        cred = None

    if cred:
        firebase_admin.initialize_app(cred)
        FIREBASE_READY = True
        print('Firebase Admin initialised')
    else:
        print('No Firebase credentials found — push notifications disabled')
except Exception as e:
    print(f'Firebase unavailable: {e}')


# ==========================================================================
# MODELS
# ==========================================================================

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(190), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    blood_group = db.Column(db.String(10), default='Not sure')
    vehicle_type = db.Column(db.String(30), default='Car')
    vehicle_number = db.Column(db.String(20))
    driving_preference = db.Column(db.String(20), default='Balanced')

    fcm_token = db.Column(db.String(255))

    # Admin and moderation
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    blocked_reason = db.Column(db.String(255))
    blocked_at = db.Column(db.DateTime)

    alert_overspeed = db.Column(db.Boolean, default=True)
    alert_hazards = db.Column(db.Boolean, default=True)
    auto_sos = db.Column(db.Boolean, default=False)
    share_location = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'blood_group': self.blood_group,
            'vehicle_type': self.vehicle_type,
            'vehicle_number': self.vehicle_number,
            'driving_preference': self.driving_preference,
            'is_admin': self.is_admin,
            'is_blocked': self.is_blocked,
            'settings': {
                'alert_overspeed': self.alert_overspeed,
                'alert_hazards': self.alert_hazards,
                'auto_sos': self.auto_sos,
                'share_location': self.share_location,
            },
        }


    def to_admin_dict(self):
        """Richer view for the admin console — counts and moderation state."""
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'blood_group': self.blood_group,
            'vehicle_type': self.vehicle_type,
            'vehicle_number': self.vehicle_number,
            'is_admin': self.is_admin,
            'is_blocked': self.is_blocked,
            'blocked_reason': self.blocked_reason,
            'joined_at': self.created_at.isoformat() if self.created_at else None,
            'guardian_count': Guardian.query.filter_by(user_id=self.id).count(),
            'hazard_count': Hazard.query.filter_by(user_id=self.id).count(),
            'journey_count': Journey.query.filter_by(user_id=self.id).count(),
            'sos_count': SosAlert.query.filter_by(user_id=self.id).count(),
        }


class Guardian(db.Model):
    __tablename__ = 'guardians'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    relation = db.Column(db.String(50), default='Contact')

    # Set when the guardian's phone number matches a registered MARG user,
    # which is how we know we can push to them rather than only calling.
    guardian_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'relation': self.relation,
            'has_app': self.guardian_user_id is not None,
        }


class Hazard(db.Model):
    __tablename__ = 'hazards'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    hazard_type = db.Column(db.String(30), nullable=False, index=True)
    severity = db.Column(db.String(20), default='Moderate')
    note = db.Column(db.Text)

    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    place_name = db.Column(db.String(255))

    confirmations = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    reporter = db.relationship('User', backref='hazards')

    def to_dict(self, distance_km=None):
        return {
            'id': self.id,
            'type': self.hazard_type,
            'severity': self.severity,
            'note': self.note,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'place_name': self.place_name,
            'confirmations': self.confirmations,
            'reported_by': self.reporter.name if self.reporter else 'Unknown',
            'reported_at': self.created_at.isoformat(),
            'age_minutes': int(
                (datetime.utcnow() - self.created_at).total_seconds() / 60
            ),
            'distance_km': round(distance_km, 2) if distance_km is not None else None,
        }


class HazardConfirmation(db.Model):
    """Stops one user confirming the same hazard repeatedly."""
    __tablename__ = 'hazard_confirmations'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hazard_id = db.Column(db.Integer, db.ForeignKey('hazards.id', ondelete='CASCADE'),
                          nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('hazard_id', 'user_id', name='uq_hazard_user'),
    )


class Journey(db.Model):
    __tablename__ = 'journeys'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)

    origin_lat = db.Column(db.Float)
    origin_lng = db.Column(db.Float)
    destination_lat = db.Column(db.Float)
    destination_lng = db.Column(db.Float)
    destination_name = db.Column(db.String(255))

    distance_km = db.Column(db.Float, default=0)
    duration_min = db.Column(db.Integer, default=0)
    top_speed_kph = db.Column(db.Float, default=0)
    overspeed_events = db.Column(db.Integer, default=0)

    status = db.Column(db.String(20), default='active')  # active | completed | abandoned
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'destination_name': self.destination_name,
            'distance_km': self.distance_km,
            'duration_min': self.duration_min,
            'top_speed_kph': self.top_speed_kph,
            'overspeed_events': self.overspeed_events,
            'status': self.status,
            'started_at': self.started_at.isoformat(),
            'ended_at': self.ended_at.isoformat() if self.ended_at else None,
        }


class SosAlert(db.Model):
    __tablename__ = 'sos_alerts'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    journey_id = db.Column(db.Integer, db.ForeignKey('journeys.id'))

    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    place_name = db.Column(db.String(255))

    trigger = db.Column(db.String(20), default='manual')  # manual | automatic
    status = db.Column(db.String(20), default='active')   # active | resolved
    guardians_notified = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    # Distinct from created_at — tells a responder how stale the pin is.
    location_updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='sos_alerts')

    def to_dict(self):
        return {
            'id': self.id,
            'user_name': self.user.name if self.user else 'Unknown',
            'blood_group': self.user.blood_group if self.user else None,
            'vehicle_number': self.user.vehicle_number if self.user else None,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'place_name': self.place_name,
            'trigger': self.trigger,
            'status': self.status,
            'guardians_notified': self.guardians_notified,
            'created_at': self.created_at.isoformat(),
        }


# ==========================================================================
# HELPERS
# ==========================================================================

def make_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=30),
        'iat': datetime.now(timezone.utc),
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')


def token_required(f):
    """Reads the Bearer token and passes the User in as the first argument."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing authorization token'}), 401

        token = auth.split(' ', 1)[1].strip()
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired, please sign in again'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401

        user = db.session.get(User, payload['user_id'])
        if not user:
            return jsonify({'error': 'User no longer exists'}), 401

        # A blocked account keeps its valid token, so the check has to happen
        # on every request rather than only at login.
        if user.is_blocked:
            return jsonify({
                'error': user.blocked_reason
                         or 'Your account has been suspended. Contact support.',
                'blocked': True,
            }), 403

        return f(user, *args, **kwargs)
    return wrapper


def admin_required(f):
    """Runs token_required first, then checks the admin flag."""
    @wraps(f)
    @token_required
    def wrapper(user, *args, **kwargs):
        if not user.is_admin:
            # 404 rather than 403 — no reason to confirm the route exists
            # to someone who shouldn't know about it.
            return jsonify({'error': 'Endpoint not found'}), 404
        return f(user, *args, **kwargs)
    return wrapper


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in kilometres."""
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalise_phone(phone):
    """Strips formatting so '+91 98400 12345' and '9840012345' can match."""
    digits = ''.join(c for c in (phone or '') if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def send_push(tokens, title, body, data=None):
    """Fan-out to a list of FCM tokens. Returns how many were accepted."""
    if not FIREBASE_READY or not tokens:
        print(f'[push skipped] {title} — {len(tokens)} recipients')
        return 0

    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    channel_id='marg_sos_channel',
                    priority='max',
                ),
            ),
            tokens=tokens,
        )
        response = messaging.send_each_for_multicast(message)

        # Clear out tokens Firebase says are dead, or they accumulate forever.
        for idx, result in enumerate(response.responses):
            if not result.success:
                err = str(result.exception)
                if 'not-registered' in err.lower() or 'invalid-argument' in err.lower():
                    stale = User.query.filter_by(fcm_token=tokens[idx]).first()
                    if stale:
                        stale.fcm_token = None
        db.session.commit()

        return response.success_count
    except Exception as e:
        print(f'Push failed: {e}')
        return 0


def link_guardians_to_users(phone, user_id):
    """
    When someone registers, connect any existing guardian entries that list
    their phone number. That's how an existing user's guardian suddenly
    becomes push-capable after installing the app.
    """
    tail = normalise_phone(phone)
    if not tail:
        return
    for g in Guardian.query.filter(Guardian.guardian_user_id.is_(None)).all():
        if normalise_phone(g.phone) == tail:
            g.guardian_user_id = user_id
    db.session.commit()


# ==========================================================================
# AUTH
# ==========================================================================

@app.route('/api/signup', methods=['POST'])
def signup():
    data = request.get_json() or {}

    required = ['name', 'email', 'phone', 'password']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f"Missing: {', '.join(missing)}"}), 400

    email = data['email'].strip().lower()

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'That email is already registered'}), 409

    if len(data['password']) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    user = User(
        name=data['name'].strip(),
        email=email,
        phone=data['phone'].strip(),
        # Hashed, never stored in plain text. No repeat_password column —
        # matching passwords is a form concern, not something to persist.
        password_hash=bcrypt.generate_password_hash(data['password']).decode('utf-8'),
        blood_group=data.get('blood_group', 'Not sure'),
        vehicle_type=data.get('vehicle_type', 'Car'),
        vehicle_number=(data.get('vehicle_number') or '').upper() or None,
        driving_preference=data.get('driving_preference', 'Balanced'),
        fcm_token=data.get('fcm_token'),
    )

    db.session.add(user)
    db.session.commit()

    link_guardians_to_users(user.phone, user.id)

    return jsonify({
        'message': 'Account created',
        'token': make_token(user.id),
        'user': user.to_dict(),
    }), 201


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'error': 'Email and password are both required'}), 400

    user = User.query.filter_by(email=email).first()

    # Deliberately the same message for both cases — telling an attacker
    # which emails exist is a free gift.
    if not user or not bcrypt.check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Incorrect email or password'}), 401

    if user.is_blocked:
        return jsonify({
            'error': user.blocked_reason
                     or 'Your account has been suspended. Contact support.',
            'blocked': True,
        }), 403

    if data.get('fcm_token'):
        user.fcm_token = data['fcm_token']
        db.session.commit()

    return jsonify({
        'message': 'Signed in',
        'token': make_token(user.id),
        'user': user.to_dict(),
    }), 200


# ==========================================================================
# PROFILE
# ==========================================================================

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(user):
    week_ago = datetime.utcnow() - timedelta(days=7)

    stats = db.session.query(
        func.coalesce(func.sum(Journey.distance_km), 0),
        func.count(Journey.id),
        func.coalesce(func.sum(Journey.overspeed_events), 0),
    ).filter(
        Journey.user_id == user.id,
        Journey.started_at >= week_ago,
        Journey.status == 'completed',
    ).first()

    payload = user.to_dict()
    payload['stats'] = {
        'distance_km': round(float(stats[0]), 1),
        'journeys': int(stats[1]),
        'overspeeds': int(stats[2]),
    }
    return jsonify(payload), 200


@app.route('/api/profile', methods=['PUT'])
@token_required
def update_profile(user):
    data = request.get_json() or {}

    for field in ['name', 'phone', 'blood_group', 'vehicle_type',
                  'driving_preference']:
        if data.get(field):
            setattr(user, field, data[field])

    if data.get('vehicle_number') is not None:
        user.vehicle_number = data['vehicle_number'].upper() or None

    settings = data.get('settings') or {}
    for field in ['alert_overspeed', 'alert_hazards', 'auto_sos', 'share_location']:
        if field in settings:
            setattr(user, field, bool(settings[field]))

    db.session.commit()
    return jsonify({'message': 'Profile updated', 'user': user.to_dict()}), 200


@app.route('/api/fcm-token', methods=['POST'])
@token_required
def update_fcm_token(user):
    """Called on every app launch — tokens rotate and stale ones silently fail."""
    data = request.get_json() or {}
    token = data.get('fcm_token')
    if not token:
        return jsonify({'error': 'fcm_token is required'}), 400

    user.fcm_token = token
    db.session.commit()
    return jsonify({'message': 'Token saved'}), 200


# ==========================================================================
# GUARDIANS
# ==========================================================================

@app.route('/api/guardians', methods=['GET'])
@token_required
def list_guardians(user):
    guardians = Guardian.query.filter_by(user_id=user.id).all()
    return jsonify([g.to_dict() for g in guardians]), 200


@app.route('/api/guardians', methods=['POST'])
@token_required
def add_guardian(user):
    data = request.get_json() or {}

    if not data.get('name') or not data.get('phone'):
        return jsonify({'error': 'Name and phone are both required'}), 400

    tail = normalise_phone(data['phone'])

    if tail == normalise_phone(user.phone):
        return jsonify({'error': 'You cannot add yourself as a guardian'}), 400

    for existing in Guardian.query.filter_by(user_id=user.id).all():
        if normalise_phone(existing.phone) == tail:
            return jsonify({'error': 'That number is already a guardian'}), 409

    # If this number belongs to a MARG user, we can push to them.
    match = None
    for candidate in User.query.all():
        if normalise_phone(candidate.phone) == tail:
            match = candidate
            break

    guardian = Guardian(
        user_id=user.id,
        name=data['name'].strip(),
        phone=data['phone'].strip(),
        relation=data.get('relation', 'Contact'),
        guardian_user_id=match.id if match else None,
    )
    db.session.add(guardian)
    db.session.commit()

    return jsonify({'message': 'Guardian added', 'guardian': guardian.to_dict()}), 201


@app.route('/api/guardians/<int:guardian_id>', methods=['DELETE'])
@token_required
def delete_guardian(user, guardian_id):
    guardian = Guardian.query.filter_by(id=guardian_id, user_id=user.id).first()
    if not guardian:
        return jsonify({'error': 'Guardian not found'}), 404

    db.session.delete(guardian)
    db.session.commit()
    return jsonify({'message': 'Guardian removed'}), 200


# ==========================================================================
# HAZARDS
# ==========================================================================

@app.route('/api/hazards', methods=['POST'])
@token_required
def report_hazard(user):
    data = request.get_json() or {}

    required = ['type', 'latitude', 'longitude']
    missing = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({'error': f"Missing: {', '.join(missing)}"}), 400

    valid = ['pothole', 'construction', 'traffic', 'accident',
             'fallen_tree', 'breakdown']
    if data['type'] not in valid:
        return jsonify({'error': f"type must be one of {valid}"}), 400

    lat, lng = float(data['latitude']), float(data['longitude'])

    # If the same hazard type was reported within 100 m in the last 6 hours,
    # treat this as a confirmation instead of creating a duplicate pin.
    recent = Hazard.query.filter(
        Hazard.hazard_type == data['type'],
        Hazard.is_active.is_(True),
        Hazard.created_at >= datetime.utcnow() - timedelta(hours=6),
    ).all()

    for h in recent:
        if haversine_km(lat, lng, h.latitude, h.longitude) < 0.1:
            already = HazardConfirmation.query.filter_by(
                hazard_id=h.id, user_id=user.id).first()
            if not already:
                db.session.add(HazardConfirmation(hazard_id=h.id, user_id=user.id))
                h.confirmations += 1
                db.session.commit()
            return jsonify({
                'message': 'Existing report confirmed',
                'hazard': h.to_dict(),
            }), 200

    hazard = Hazard(
        user_id=user.id,
        hazard_type=data['type'],
        severity=data.get('severity', 'Moderate'),
        note=data.get('note'),
        latitude=lat,
        longitude=lng,
        place_name=data.get('place_name'),
    )
    db.session.add(hazard)
    db.session.commit()

    return jsonify({'message': 'Hazard reported', 'hazard': hazard.to_dict()}), 201


@app.route('/api/hazards/nearby', methods=['GET'])
@token_required
def nearby_hazards(user):
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'error': 'lat and lng query params are required'}), 400

    radius = float(request.args.get('radius_km', 10))

    # Bounding box first so MySQL can use the lat/lng indexes, then exact
    # haversine in Python. Filtering purely in Python would scan every row.
    lat_delta = radius / 111.0
    lng_delta = radius / (111.0 * max(math.cos(math.radians(lat)), 0.01))

    cutoff = datetime.utcnow() - timedelta(hours=24)

    candidates = Hazard.query.filter(
        Hazard.is_active.is_(True),
        Hazard.created_at >= cutoff,
        Hazard.latitude.between(lat - lat_delta, lat + lat_delta),
        Hazard.longitude.between(lng - lng_delta, lng + lng_delta),
    ).all()

    results = []
    for h in candidates:
        d = haversine_km(lat, lng, h.latitude, h.longitude)
        if d <= radius:
            results.append(h.to_dict(distance_km=d))

    results.sort(key=lambda x: x['distance_km'])
    return jsonify(results), 200


@app.route('/api/hazards/<int:hazard_id>/confirm', methods=['POST'])
@token_required
def confirm_hazard(user, hazard_id):
    hazard = db.session.get(Hazard, hazard_id)
    if not hazard:
        return jsonify({'error': 'Hazard not found'}), 404

    if HazardConfirmation.query.filter_by(hazard_id=hazard_id, user_id=user.id).first():
        return jsonify({'error': 'You already confirmed this'}), 409

    db.session.add(HazardConfirmation(hazard_id=hazard_id, user_id=user.id))
    hazard.confirmations += 1
    db.session.commit()

    return jsonify({'message': 'Confirmed', 'hazard': hazard.to_dict()}), 200


@app.route('/api/hazards/<int:hazard_id>/clear', methods=['POST'])
@token_required
def clear_hazard(user, hazard_id):
    """Marks a hazard as gone. Only the original reporter can do this."""
    hazard = Hazard.query.filter_by(id=hazard_id, user_id=user.id).first()
    if not hazard:
        return jsonify({'error': 'Hazard not found, or not yours to clear'}), 404

    hazard.is_active = False
    db.session.commit()
    return jsonify({'message': 'Hazard cleared'}), 200


# ==========================================================================
# JOURNEYS
# ==========================================================================

@app.route('/api/journeys/start', methods=['POST'])
@token_required
def start_journey(user):
    data = request.get_json() or {}

    # Close any journey left hanging by a crash or force-quit.
    Journey.query.filter_by(user_id=user.id, status='active').update(
        {'status': 'abandoned', 'ended_at': datetime.utcnow()}
    )

    journey = Journey(
        user_id=user.id,
        origin_lat=data.get('origin_lat'),
        origin_lng=data.get('origin_lng'),
        destination_lat=data.get('destination_lat'),
        destination_lng=data.get('destination_lng'),
        destination_name=data.get('destination_name'),
        distance_km=data.get('distance_km', 0),
        duration_min=data.get('duration_min', 0),
    )
    db.session.add(journey)
    db.session.commit()

    return jsonify({'message': 'Journey started', 'journey': journey.to_dict()}), 201


@app.route('/api/journeys/<int:journey_id>/end', methods=['POST'])
@token_required
def end_journey(user, journey_id):
    journey = Journey.query.filter_by(id=journey_id, user_id=user.id).first()
    if not journey:
        return jsonify({'error': 'Journey not found'}), 404

    data = request.get_json() or {}

    journey.status = 'completed'
    journey.ended_at = datetime.utcnow()
    journey.top_speed_kph = data.get('top_speed_kph', journey.top_speed_kph)
    journey.overspeed_events = data.get('overspeed_events', journey.overspeed_events)
    if data.get('distance_km'):
        journey.distance_km = data['distance_km']

    elapsed = (journey.ended_at - journey.started_at).total_seconds() / 60
    journey.duration_min = int(elapsed)

    db.session.commit()
    return jsonify({'message': 'Journey completed', 'journey': journey.to_dict()}), 200


@app.route('/api/journeys', methods=['GET'])
@token_required
def journey_history(user):
    limit = min(int(request.args.get('limit', 20)), 100)
    journeys = Journey.query.filter_by(user_id=user.id) \
        .order_by(Journey.started_at.desc()).limit(limit).all()
    return jsonify([j.to_dict() for j in journeys]), 200


# ==========================================================================
# SOS
# ==========================================================================

@app.route('/api/sos', methods=['POST'])
@token_required
def trigger_sos(user):
    """
    The core of the app. Creates the alert, then pushes to every guardian
    who has MARG installed.
    """
    data = request.get_json() or {}

    if data.get('latitude') is None or data.get('longitude') is None:
        return jsonify({'error': 'latitude and longitude are required'}), 400

    active_journey = Journey.query.filter_by(
        user_id=user.id, status='active').first()

    alert = SosAlert(
        user_id=user.id,
        journey_id=active_journey.id if active_journey else None,
        latitude=float(data['latitude']),
        longitude=float(data['longitude']),
        place_name=data.get('place_name'),
        trigger=data.get('trigger', 'manual'),
    )
    db.session.add(alert)
    db.session.commit()

    # Collect FCM tokens for guardians who are also MARG users.
    guardians = Guardian.query.filter_by(user_id=user.id).all()
    tokens = []
    for g in guardians:
        if g.guardian_user_id:
            gu = db.session.get(User, g.guardian_user_id)
            if gu and gu.fcm_token:
                tokens.append(gu.fcm_token)

    location = alert.place_name or f"{alert.latitude:.4f}, {alert.longitude:.4f}"
    sent = send_push(
        tokens,
        title=f'{user.name} needs help',
        body=f'SOS triggered near {location}. Tap to see their location.',
        data={
            'type': 'sos',
            'alert_id': alert.id,
            'lat': alert.latitude,
            'lng': alert.longitude,
            'user_name': user.name,
            'blood_group': user.blood_group or '',
            'vehicle_number': user.vehicle_number or '',
        },
    )

    alert.guardians_notified = sent
    db.session.commit()

    return jsonify({
        'message': 'SOS sent',
        'alert': alert.to_dict(),
        'guardians_total': len(guardians),
        'guardians_notified': sent,
    }), 201


@app.route('/api/sos/<int:alert_id>/resolve', methods=['POST'])
@token_required
def resolve_sos(user, alert_id):
    alert = SosAlert.query.filter_by(id=alert_id, user_id=user.id).first()
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404

    alert.status = 'resolved'
    alert.resolved_at = datetime.utcnow()
    db.session.commit()

    # Let guardians know they can stand down.
    tokens = []
    for g in Guardian.query.filter_by(user_id=user.id).all():
        if g.guardian_user_id:
            gu = db.session.get(User, g.guardian_user_id)
            if gu and gu.fcm_token:
                tokens.append(gu.fcm_token)

    send_push(
        tokens,
        title=f'{user.name} is safe',
        body='The SOS has been stood down.',
        data={'type': 'sos_resolved', 'alert_id': alert.id},
    )

    return jsonify({'message': 'SOS resolved', 'alert': alert.to_dict()}), 200


@app.route('/api/sos/<int:alert_id>/location', methods=['POST'])
@token_required
def update_sos_location(user, alert_id):
    """
    The person in trouble pushes their position while the alert is open, so
    guardians watching the responder map see them move rather than a pin
    frozen where the SOS was first triggered.
    """
    alert = SosAlert.query.filter_by(id=alert_id, user_id=user.id).first()
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404

    if alert.status != 'active':
        return jsonify({'error': 'That alert is already resolved'}), 400

    data = request.get_json() or {}
    if data.get('latitude') is None or data.get('longitude') is None:
        return jsonify({'error': 'latitude and longitude are required'}), 400

    alert.latitude = float(data['latitude'])
    alert.longitude = float(data['longitude'])
    if data.get('place_name'):
        alert.place_name = data['place_name']
    alert.location_updated_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Location updated'}), 200


@app.route('/api/sos/<int:alert_id>', methods=['GET'])
@token_required
def get_sos_alert(user, alert_id):
    """
    Detail for the responder map. Readable by the person who raised it, by
    any of their guardians, and by an admin — nobody else, since this hands
    out someone's live position.
    """
    alert = db.session.get(SosAlert, alert_id)
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404

    is_owner = alert.user_id == user.id
    is_guardian = Guardian.query.filter_by(
        user_id=alert.user_id, guardian_user_id=user.id).first() is not None

    if not (is_owner or is_guardian or user.is_admin):
        return jsonify({'error': 'Alert not found'}), 404

    payload = alert.to_dict()
    payload['user_phone'] = alert.user.phone if alert.user else None
    payload['location_updated_at'] = (
        alert.location_updated_at.isoformat()
        if alert.location_updated_at else alert.created_at.isoformat()
    )
    payload['seconds_since_update'] = int(
        (datetime.utcnow() -
         (alert.location_updated_at or alert.created_at)).total_seconds()
    )
    payload['viewer_is_owner'] = is_owner
    return jsonify(payload), 200


@app.route('/api/sos/incoming', methods=['GET'])
@token_required
def incoming_alerts(user):
    """Active alerts from people who listed this user as their guardian."""
    links = Guardian.query.filter_by(guardian_user_id=user.id).all()
    owner_ids = [g.user_id for g in links]

    if not owner_ids:
        return jsonify([]), 200

    alerts = SosAlert.query.filter(
        SosAlert.user_id.in_(owner_ids),
        SosAlert.status == 'active',
    ).order_by(SosAlert.created_at.desc()).all()

    results = []
    for a in alerts:
        item = a.to_dict()
        item['user_phone'] = a.user.phone if a.user else None
        item['seconds_since_update'] = int(
            (datetime.utcnow() -
             (a.location_updated_at or a.created_at)).total_seconds()
        )
        results.append(item)

    return jsonify(results), 200


@app.route('/api/sos/history', methods=['GET'])
@token_required
def sos_history(user):
    alerts = SosAlert.query.filter_by(user_id=user.id) \
        .order_by(SosAlert.created_at.desc()).limit(20).all()
    return jsonify([a.to_dict() for a in alerts]), 200



# ==========================================================================
# ADMIN
#
# Every route here sits behind @admin_required, which returns 404 rather
# than 403 to a non-admin — there's no value in confirming these exist.
#
# To make the first admin, run this in phpMyAdmin after signing up:
#     UPDATE users SET is_admin = 1 WHERE email = 'your@email.com';
# ==========================================================================

@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def admin_stats(admin):
    day_ago = datetime.utcnow() - timedelta(days=1)
    week_ago = datetime.utcnow() - timedelta(days=7)

    return jsonify({
        'users': {
            'total': User.query.count(),
            'blocked': User.query.filter_by(is_blocked=True).count(),
            'new_this_week': User.query.filter(User.created_at >= week_ago).count(),
        },
        'sos': {
            'active': SosAlert.query.filter_by(status='active').count(),
            'today': SosAlert.query.filter(SosAlert.created_at >= day_ago).count(),
            'total': SosAlert.query.count(),
        },
        'hazards': {
            'active': Hazard.query.filter_by(is_active=True).count(),
            'today': Hazard.query.filter(Hazard.created_at >= day_ago).count(),
            'total': Hazard.query.count(),
        },
        'journeys': {
            'in_progress': Journey.query.filter_by(status='active').count(),
            'this_week': Journey.query.filter(Journey.started_at >= week_ago).count(),
            'total': Journey.query.count(),
        },
    }), 200


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_list_users(admin):
    search = (request.args.get('q') or '').strip()
    status = request.args.get('status', 'all')   # all | active | blocked
    limit = min(int(request.args.get('limit', 50)), 200)

    query = User.query

    if search:
        like = f'%{search}%'
        query = query.filter(
            db.or_(User.name.like(like), User.email.like(like),
                   User.phone.like(like))
        )

    if status == 'blocked':
        query = query.filter_by(is_blocked=True)
    elif status == 'active':
        query = query.filter_by(is_blocked=False)

    users = query.order_by(User.created_at.desc()).limit(limit).all()
    return jsonify([u.to_admin_dict() for u in users]), 200


@app.route('/api/admin/users/<int:user_id>', methods=['GET'])
@admin_required
def admin_user_detail(admin, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    payload = user.to_admin_dict()
    payload['recent_sos'] = [
        a.to_dict() for a in SosAlert.query.filter_by(user_id=user_id)
        .order_by(SosAlert.created_at.desc()).limit(5).all()
    ]
    payload['recent_journeys'] = [
        j.to_dict() for j in Journey.query.filter_by(user_id=user_id)
        .order_by(Journey.started_at.desc()).limit(5).all()
    ]
    return jsonify(payload), 200


@app.route('/api/admin/users/<int:user_id>/block', methods=['POST'])
@admin_required
def admin_block_user(admin, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    # Two guards worth having: an admin locking themselves out is
    # unrecoverable without database access, and admins blocking each
    # other turns a moderation tool into a weapon.
    if user.id == admin.id:
        return jsonify({'error': 'You cannot block your own account'}), 400
    if user.is_admin:
        return jsonify({'error': 'Admin accounts cannot be blocked'}), 400

    data = request.get_json() or {}
    user.is_blocked = True
    user.blocked_reason = data.get('reason') or 'Account suspended by an administrator.'
    user.blocked_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': f'{user.name} blocked', 'user': user.to_admin_dict()}), 200


@app.route('/api/admin/users/<int:user_id>/unblock', methods=['POST'])
@admin_required
def admin_unblock_user(admin, user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    db.session.commit()

    return jsonify({'message': f'{user.name} unblocked', 'user': user.to_admin_dict()}), 200


@app.route('/api/admin/sos', methods=['GET'])
@admin_required
def admin_list_sos(admin):
    status = request.args.get('status', 'all')   # all | active | resolved
    limit = min(int(request.args.get('limit', 50)), 200)

    query = SosAlert.query
    if status in ('active', 'resolved'):
        query = query.filter_by(status=status)

    alerts = query.order_by(SosAlert.created_at.desc()).limit(limit).all()

    results = []
    for a in alerts:
        item = a.to_dict()
        item['user_id'] = a.user_id
        item['user_phone'] = a.user.phone if a.user else None
        item['resolved_at'] = a.resolved_at.isoformat() if a.resolved_at else None
        results.append(item)

    return jsonify(results), 200


@app.route('/api/admin/sos/<int:alert_id>/resolve', methods=['POST'])
@admin_required
def admin_resolve_sos(admin, alert_id):
    """Lets an admin stand down an alert the user forgot to close."""
    alert = db.session.get(SosAlert, alert_id)
    if not alert:
        return jsonify({'error': 'Alert not found'}), 404

    alert.status = 'resolved'
    alert.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'Alert resolved', 'alert': alert.to_dict()}), 200


@app.route('/api/admin/hazards', methods=['GET'])
@admin_required
def admin_list_hazards(admin):
    status = request.args.get('status', 'active')  # active | cleared | all
    limit = min(int(request.args.get('limit', 100)), 300)

    query = Hazard.query
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'cleared':
        query = query.filter_by(is_active=False)

    hazards = query.order_by(Hazard.created_at.desc()).limit(limit).all()

    results = []
    for h in hazards:
        item = h.to_dict()
        item['is_active'] = h.is_active
        item['reporter_id'] = h.user_id
        results.append(item)

    return jsonify(results), 200


@app.route('/api/admin/hazards/<int:hazard_id>', methods=['DELETE'])
@admin_required
def admin_delete_hazard(admin, hazard_id):
    """Removes a false or malicious report outright."""
    hazard = db.session.get(Hazard, hazard_id)
    if not hazard:
        return jsonify({'error': 'Hazard not found'}), 404

    db.session.delete(hazard)
    db.session.commit()
    return jsonify({'message': 'Hazard deleted'}), 200


@app.route('/api/admin/hazards/<int:hazard_id>/clear', methods=['POST'])
@admin_required
def admin_clear_hazard(admin, hazard_id):
    """Marks it resolved but keeps the record, unlike delete."""
    hazard = db.session.get(Hazard, hazard_id)
    if not hazard:
        return jsonify({'error': 'Hazard not found'}), 404

    hazard.is_active = False
    db.session.commit()
    return jsonify({'message': 'Hazard cleared'}), 200


@app.route('/api/admin/broadcast', methods=['POST'])
@admin_required
def admin_broadcast(admin):
    """Pushes a safety notice to every user with a live FCM token."""
    data = request.get_json() or {}
    title = data.get('title')
    body = data.get('body')

    if not title or not body:
        return jsonify({'error': 'title and body are both required'}), 400

    tokens = [u.fcm_token for u in
              User.query.filter(User.fcm_token.isnot(None),
                                User.is_blocked.is_(False)).all()
              if u.fcm_token]

    # FCM caps multicast at 500 tokens per call, so send in batches.
    sent = 0
    for i in range(0, len(tokens), 500):
        sent += send_push(tokens[i:i + 500], title, body,
                          data={'type': 'broadcast'})

    return jsonify({
        'message': 'Broadcast sent',
        'recipients': len(tokens),
        'delivered': sent,
    }), 200


# ==========================================================================
# HEALTH
# ==========================================================================

@app.route('/', methods=['GET'])
def health():
    return jsonify({
        'service': 'MARG API',
        'status': 'running',
        'firebase': FIREBASE_READY,
        'time': datetime.utcnow().isoformat(),
    }), 200


@app.errorhandler(404)
def not_found(_):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(_):
    db.session.rollback()
    return jsonify({'error': 'Something went wrong on the server'}), 500



def seed_admin():
    """
    Creates the admin account on first startup if it doesn't exist.

    Credentials come from environment variables so they can be changed
    without touching code. The defaults are fine for local development;
    set ADMIN_EMAIL and ADMIN_PASSWORD on Railway before deploying, or
    anyone who has read this file can sign in as administrator.

    Note this creates a real user row with a bcrypt-hashed password — it
    is not a hardcoded bypass in the login route. That matters because the
    admin needs a genuine id for the "can't block yourself" and "can't
    block another admin" guards to work.
    """
    email = os.environ.get('ADMIN_EMAIL', 'admin@gmail.com').lower()
    password = os.environ.get('ADMIN_PASSWORD', 'admin123')

    existing = User.query.filter_by(email=email).first()

    if existing:
        # Promote it if someone signed up with that address normally.
        if not existing.is_admin:
            existing.is_admin = True
            db.session.commit()
            print(f'Promoted existing account to admin: {email}')
        return

    admin = User(
        name=os.environ.get('ADMIN_NAME', 'Administrator'),
        email=email,
        phone=os.environ.get('ADMIN_PHONE', '0000000000'),
        password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
        is_admin=True,
        blood_group='Not sure',
        vehicle_type='Car',
    )
    db.session.add(admin)
    db.session.commit()

    print('=' * 58)
    print(f'  Admin account ready: {email}')
    if password == 'admin123':
        print('  Password is the default. Set ADMIN_PASSWORD before deploying.')
    print('=' * 58)


def initialise():
    """
    Creates tables and the admin account.

    This runs at import time, not just under __main__, because gunicorn
    imports the module rather than executing it — so anything inside the
    __main__ block never runs on Railway, and the app would start against
    an empty database.
    """
    try:
        with app.app_context():
            db.create_all()
            print('Tables ready')
            seed_admin()
    except Exception as e:
        # Don't take the whole process down if the database is still waking
        # up; the first request will retry the connection.
        print(f'Startup initialisation deferred: {e}')


initialise()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug, host='0.0.0.0', port=port)
