from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from models import db, User, Medicine, Sale
from config import Config
import os

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# Create DB and a default admin if not exists
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email="admin@pms.local").first():
        admin = User(
            name="Administrator",
            email="admin@pms.local",
            role="admin",
            password_hash=generate_password_hash("admin123")
        )
        db.session.add(admin)
        db.session.commit()

# --- Helpers ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Login required", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def current_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

# --- Routes ---
@app.route("/")
def index():
    user = current_user()
    return render_template("index.html", user=user)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        pwd = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, pwd):
            session["user_id"] = user.id
            flash(f"Welcome {user.name}", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("index"))

# Add pharmacist (admin)
@app.route("/admin/add_pharmacist", methods=["GET","POST"])
@login_required
def add_pharmacist():
    user = current_user()
    if user.role != "admin":
        flash("Admin access only", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        role = request.form.get("role","pharmacist")
        pwd = request.form["password"] or "pharma123"
        if User.query.filter_by(email=email).first():
            flash("Email already exists", "warning")
        else:
            new = User(name=name, email=email, role=role, password_hash=generate_password_hash(pwd))
            db.session.add(new); db.session.commit()
            flash("Pharmacist added", "success")
            return redirect(url_for("inventory"))
    return render_template("add_pharmacist.html", user=user)

# Add medicine
@app.route("/admin/add_medicine", methods=["GET","POST"])
@login_required
def add_medicine():
    user = current_user()
    if user.role not in ("admin","pharmacist"):
        flash("Not authorized", "danger")
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form["name"].strip()
        batch = request.form.get("batch","")
        expiry_str = request.form["expiry"]
        price = float(request.form["price"])
        qty = int(request.form["quantity"])
        try:
            expiry = datetime.strptime(expiry_str, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format. Use YYYY-MM-DD", "warning")
            return redirect(url_for("add_medicine"))
        med = Medicine(name=name, batch=batch, expiry=expiry, price=price, quantity=qty)
        db.session.add(med); db.session.commit()
        flash("Medicine added/updated", "success")
        return redirect(url_for("inventory"))
    return render_template("add_medicine.html", user=user)

# Inventory listing & search
@app.route("/inventory")
@login_required
def inventory():
    q = request.args.get("q","").strip()
    if q:
        meds = Medicine.query.filter(Medicine.name.ilike(f"%{q}%")).order_by(Medicine.name).all()
    else:
        meds = Medicine.query.order_by(Medicine.name).all()
    user = current_user()
    return render_template("inventory.html", meds=meds, user=user, q=q)

# Sell medicine (create sale)
@app.route("/sell", methods=["GET","POST"])
@login_required
def sell():
    user = current_user()
    meds = Medicine.query.order_by(Medicine.name).all()
    if request.method == "POST":
        med_id = int(request.form["medicine_id"])
        qty = int(request.form["quantity"])
        med = Medicine.query.get(med_id)
        if not med:
            flash("Medicine not found", "danger")
            return redirect(url_for("sell"))
        if med.quantity < qty:
            flash("Insufficient stock", "warning")
            return redirect(url_for("sell"))
        total = qty * med.price
        sale = Sale(medicine_id=med.id, qty=qty, total_price=total)
        med.quantity -= qty
        db.session.add(sale)
        db.session.commit()
        flash(f"Sold {qty} x {med.name}. Total ₹{total:.2f}", "success")
        return redirect(url_for("inventory"))
    return render_template("sell.html", meds=meds, user=user)

# Alerts for expiry and low stock
@app.route("/alerts")
@login_required
def alerts():
    today = date.today()
    near = today + timedelta(days=30)  # within next 30 days
    expired = Medicine.query.filter(Medicine.expiry < today).order_by(Medicine.expiry).all()
    expiring_soon = Medicine.query.filter(Medicine.expiry.between(today, near)).order_by(Medicine.expiry).all()
    low_stock = Medicine.query.filter(Medicine.quantity <= 5).order_by(Medicine.quantity).all()
    user = current_user()
    return render_template("alerts.html", expired=expired, expiring_soon=expiring_soon, low_stock=low_stock, user=user)

# Simple route to initialize demo data (optional)
@app.route("/init_demo")
def init_demo():
    if Medicine.query.count() == 0:
        demo = [
            Medicine(name="Paracetamol", batch="A101", expiry=date.today().replace(year=date.today().year+1), price=20.0, quantity=50),
            Medicine(name="Amoxicillin", batch="B201", expiry=date.today().replace(year=date.today().year+2), price=45.0, quantity=30),
            Medicine(name="Aspirin", batch="C301", expiry=date.today().replace(year=date.today().year+1), price=15.0, quantity=10),
        ]
        db.session.bulk_save_objects(demo)
        db.session.commit()
    return redirect(url_for("inventory"))

# Run app
if __name__ == "__main__":
    app.secret_key = app.config["SECRET_KEY"]
    app.run(debug=True)
