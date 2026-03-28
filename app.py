import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for, flash
from sqlalchemy import inspect, or_
from functools import wraps

from models import (
    db, User, SupplierProfile, CostCenter, RequestRFQ, 
    RequestItem, Bid, BidLine, ItemAward, ItemReceipt, AllowedSupplier
)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "app.db"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key-change-this-in-prod"

db.init_app(app)

# ---------------- Helpers & Decorators ----------------
def require_roles(*roles):
    def wrap(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            if session.get("role") not in roles:
                flash("Δεν έχεις δικαίωμα πρόσβασης.", "danger")
                return redirect(url_for("login"))
            return fn(*args, **kwargs)
        return inner
    return wrap

def require_role(role):
    return require_roles(role)

def is_editable_by_current_user(rfq: "RequestRFQ") -> bool:
    if session.get("name") != rfq.created_by:
        return False
    return rfq.status == "pending"

def get_phase_key(rfq: "RequestRFQ") -> str:
    if rfq.status == "denied": return "denied"
    if rfq.status == "pending": return "awaiting_approval"
    if rfq.status == "closed":
        return "received" if rfq.winning_bid_id else "closed"
    if rfq.status == "open":
        if rfq.winning_bid_id: return "awarded"
        count_bids = len(rfq.bids or [])
        return "offers_received" if count_bids > 0 else "awaiting_offers"
    return rfq.status

def phase_info(rfq: "RequestRFQ"):
    key = get_phase_key(rfq)
    mapping = {
        "awaiting_approval": {"label": "Προς Έγκριση", "badge": "badge bg-warning text-dark", "icon": "bi-hourglass-split"},
        "awaiting_offers": {"label": "Αναμονή Προσφορών", "badge": "badge bg-info text-dark", "icon": "bi-inbox"},
        "offers_received": {"label": "Υποβλήθηκαν Προσφορές", "badge": "badge bg-primary", "icon": "bi-envelope-check"},
        "awarded": {"label": "Ανατέθηκε", "badge": "badge bg-success", "icon": "bi-trophy"},
        "received": {"label": "Παραλήφθηκε", "badge": "badge bg-success", "icon": "bi-box-seam"},
        "denied": {"label": "Απορρίφθηκε", "badge": "badge bg-danger", "icon": "bi-x-circle"},
        "closed": {"label": "Κλειστό", "badge": "badge bg-secondary", "icon": "bi-door-closed"},
    }
    info = mapping.get(key, {"label": key.title(), "badge": "badge bg-secondary", "icon": "bi-circle"})
    info["key"] = key
    return info

@app.context_processor
def utility_processor():
    return dict(phase_info=phase_info, is_editable_by_current_user=is_editable_by_current_user, now=datetime.utcnow())

# ---------------- Routes ----------------
@app.route("/")
def index():
    if session.get("role") in ["company", "chief"]:
        return redirect(url_for("company_dashboard"))
    if session.get("role") == "supplier":
        return redirect(url_for("supplier_dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = (request.form.get("password") or "").strip()
        db_user = User.query.filter_by(username=u).first()
        if not db_user or not db_user.is_active or not db_user.check_password(p):
            flash("Λάθος στοιχεία ή ανενεργός χρήστης.", "danger")
        else:
            session["name"] = db_user.display_name
            session["username"] = db_user.username
            session["role"] = db_user.role
            db_user.last_login_at = datetime.utcnow()
            db.session.commit()
            flash(f"Καλώς ήρθες, {session['name']}!", "success")
            return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Αποσύνδεση ολοκληρώθηκε.", "info")
    return redirect(url_for("login"))

@app.route("/company")
@require_roles("company", "chief")
def company_dashboard():
    phase = (request.args.get("phase") or "all").strip().lower()
    q = (request.args.get("q") or "").strip()
    qry = RequestRFQ.query
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(RequestRFQ.title.ilike(like), RequestRFQ.description.ilike(like)))
    rfqs = qry.order_by(RequestRFQ.id.desc()).all()

    editable_ids = {r.id for r in rfqs if is_editable_by_current_user(r)}
    phase_map = {r.id: phase_info(r) for r in rfqs}

    if phase != "all":
        rfqs = [r for r in rfqs if phase_map[r.id]["key"] == phase]

    return render_template("company_dash.html", rfqs=rfqs, editable_ids=editable_ids, phase=phase, q=q, phase_map=phase_map)

@app.route("/company/requests/new", methods=["GET", "POST"])
@require_roles("company", "chief")
def new_request():
    suppliers = User.query.filter_by(role='supplier', is_active=True).order_by(User.display_name.asc()).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.code.asc()).all()

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        location = (request.form.get("delivery_location") or "").strip()
        r_manager = (request.form.get("receiving_manager") or "").strip() # <--- ΝΕΟ
        phone = (request.form.get("phone") or "").strip()                 # <--- ΝΕΟ
        details = (request.form.get("details") or "").strip()
        cc_id = request.form.get("cost_center")
        
        try:
            s_deadline = datetime.strptime(request.form.get("submit_deadline"), "%Y-%m-%d")
            d_deadline = datetime.strptime(request.form.get("delivery_deadline"), "%Y-%m-%d")
        except (ValueError, TypeError):
            flash("Μη έγκυρη ημερομηνία.", "danger")
            return redirect(url_for("new_request"))

        if d_deadline < s_deadline:
            flash("Η ημερομηνία παράδοσης δεν μπορεί να είναι νωρίτερα από την ημερομηνία υποβολής.", "danger")
            return redirect(url_for("new_request"))

        selected_suppliers = request.form.getlist("suppliers[]")
        if not selected_suppliers:
            flash("Επίλεξε τουλάχιστον έναν προμηθευτή.", "danger")
            return redirect(url_for("new_request"))

        if not cc_id:
            flash("Επίλεξε Έργο/Κέντρο Κόστους.", "danger")
            return redirect(url_for("new_request"))

        rfq = RequestRFQ(
            title=title,
            description=details,
            created_by=session.get("name", "Employee"),
            delivery_location=location,
            receiving_manager=r_manager,
            phone=phone,                  
            submit_deadline=s_deadline,
            delivery_deadline=d_deadline,
            cost_center_id=int(cc_id),
            status="pending"
        )
        db.session.add(rfq)
        db.session.flush()

        desc_list = request.form.getlist("item_desc[]")
        unit_list = request.form.getlist("item_unit[]")
        qty_list = request.form.getlist("item_qty[]")

        has_items = False
        for d, u, q in zip(desc_list, unit_list, qty_list):
            if d.strip() and float(q or 0) > 0:
                db.session.add(RequestItem(request_id=rfq.id, description=d, unit=u, quantity=float(q)))
                has_items = True
        
        if not has_items:
            db.session.rollback()
            flash("Πρέπει να προσθέσεις τουλάχιστον ένα είδος.", "danger")
            return redirect(url_for("new_request"))

        for uname in selected_suppliers:
            db.session.add(AllowedSupplier(request_id=rfq.id, supplier_username=uname))

        docs = request.form.getlist("docs[]")
        if docs:
            labels = {"tech_specs":"Τεχνικές προδιαγραφές","iso":"Πιστοποιήσεις ISO","warranty":"Εγγύηση"}
            rfq.documents = ", ".join(labels.get(d, d) for d in docs)

        db.session.commit()
        flash("Η ζήτηση δημιουργήθηκε επιτυχώς.", "success")
        return redirect(url_for("company_dashboard"))

    suppliers_list = [(u.username, u.display_name) for u in suppliers]
    return render_template("new_request.html", suppliers=suppliers_list, cost_centers=cost_centers)

@app.route("/company/requests/<int:req_id>")
@require_roles("company", "chief")
def company_request_detail(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    bids = Bid.query.filter_by(request_id=req_id).order_by(Bid.price.asc()).all()
    
    awards = {aw.request_item_id: aw for aw in ItemAward.query.filter_by(request_id=rfq.id).all()}
    receipts = {r.request_item_id: r for r in ItemReceipt.query.filter_by(request_id=rfq.id).all()}
    
    items_count = len(rfq.items)
    awarded_count = len(awards)
    received_count = len(receipts)
    
    is_fully_awarded = (items_count > 0 and awarded_count == items_count) or rfq.winning_bid_id is not None
    is_fully_received = (items_count > 0 and received_count == items_count)
    current_award_total = sum(aw.line_total or 0 for aw in awards.values())

    invited_usernames = [a.supplier_username for a in rfq.allowed_suppliers]
    invited_suppliers = User.query.filter(User.username.in_(invited_usernames)).all()

    financial_summary = []
    grand_total_final = Decimal(0)
    involved_bids = {} 
    
    for aw in awards.values():
        if aw.bid_id not in involved_bids:
            involved_bids[aw.bid_id] = {'bid': aw.bid, 'item_total': Decimal(0)}
        involved_bids[aw.bid_id]['item_total'] += (aw.line_total or Decimal(0))

    for bid_id, data in involved_bids.items():
        bid = data['bid']
        item_total = data['item_total']
        
        shipping = bid.shipping_cost or Decimal(0)
        vat_pct = bid.vat_pct or Decimal(0)
        
        taxable = item_total + shipping
        vat_amount = taxable * (vat_pct / 100)
        
        total_supplier = taxable + vat_amount
        
        financial_summary.append({
            'supplier': bid.supplier_name,
            'items_cost': item_total,
            'shipping': shipping,
            'vat': vat_amount,
            'total': total_supplier
        })
        grand_total_final += total_supplier

    summary_data = []
    for item in rfq.items:
        if item.id in awards:
            aw = awards[item.id]
            summary_data.append({
                'item_desc': item.description,
                'qty': aw.qty,
                'supplier': aw.supplier_name,
                'unit_price': aw.unit_price,
                'total': aw.line_total
            })

    return render_template(
        "company_request_detail.html",
        rfq=rfq, bids=bids, awards=awards, receipts=receipts,
        is_fully_awarded=is_fully_awarded, is_fully_received=is_fully_received,
        current_award_total=current_award_total, invited_suppliers=invited_suppliers,
        summary_data=summary_data, financial_summary=financial_summary, grand_total_final=grand_total_final
    )

@app.route("/company/requests/<int:req_id>/award_item", methods=["POST"])
@require_roles("company", "chief")
def award_item(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    item_id = request.form.get("request_item_id")
    bid_line_id = request.form.get("bid_line_id")
    
    if not item_id or not bid_line_id:
        flash("Λείπουν στοιχεία για την ανάθεση.", "danger")
        return redirect(url_for('company_request_detail', req_id=req_id))
        
    bid_line = BidLine.query.get(bid_line_id)
    bid = bid_line.bid
    
    award = ItemAward.query.filter_by(request_item_id=item_id).first()
    if not award:
        award = ItemAward(request_id=rfq.id, request_item_id=item_id)
        db.session.add(award)
        
    award.bid_id = bid.id
    award.bid_line_id = bid_line.id
    award.supplier_name = bid.supplier_name
    award.qty = bid_line.qty
    award.unit_price = bid_line.unit_price
    award.line_total = bid_line.line_total
    
    db.session.commit()
    flash(f"Το είδος ανατέθηκε στον {bid.supplier_name}.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/company/requests/<int:req_id>/unaward_item", methods=["POST"])
@require_roles("company", "chief")
def unaward_item(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    item_id = request.form.get("request_item_id")
    award = ItemAward.query.filter_by(request_item_id=item_id, request_id=rfq.id).first()
    if award:
        db.session.delete(award)
        db.session.commit()
        flash("Η επιλογή αφαιρέθηκε.", "info")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/company/requests/<int:req_id>/finalize_award", methods=["POST"])
@require_roles("company", "chief")
def finalize_award(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    awards_count = ItemAward.query.filter_by(request_id=rfq.id).count()
    if awards_count == 0:
        flash("Δεν έχετε επιλέξει κανένα είδος για ανάθεση.", "warning")
        return redirect(url_for('company_request_detail', req_id=req_id))

    rfq.status = 'closed'
    db.session.commit()
    flash("Η ανάθεση οριστικοποιήθηκε. Η ζήτηση έκλεισε.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/company/requests/<int:req_id>/delete", methods=["POST"])
@require_roles("company", "chief")
def delete_request(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    db.session.delete(rfq)
    db.session.commit()
    flash("Η ζήτηση διαγράφηκε.", "warning")
    return redirect(url_for("company_dashboard"))

@app.route("/company/requests/<int:req_id>/edit", methods=["GET", "POST"])
@require_roles("company", "chief")
def edit_request(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    if not is_editable_by_current_user(rfq):
        flash("Δεν επιτρέπεται η επεξεργασία.", "danger")
        return redirect(url_for('company_request_detail', req_id=req_id))
    
    suppliers_all = User.query.filter_by(role='supplier', is_active=True).all()
    cost_centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.code.asc()).all()

    if request.method == "POST":
        rfq.title = request.form.get("title")
        rfq.delivery_location = request.form.get("delivery_location")
        rfq.description = request.form.get("details")
        
        cc_id = request.form.get("cost_center")
        if cc_id:
            rfq.cost_center_id = int(cc_id)
        
        try:
            s_deadline = datetime.strptime(request.form.get("submit_deadline"), "%Y-%m-%d")
            d_deadline = datetime.strptime(request.form.get("delivery_deadline"), "%Y-%m-%d")
            if d_deadline < s_deadline:
                flash("Η ημερομηνία παράδοσης δεν μπορεί να είναι νωρίτερα από την ημερομηνία υποβολής.", "danger")
                return redirect(url_for('edit_request', req_id=req_id))
                
            rfq.submit_deadline = s_deadline
            rfq.delivery_deadline = d_deadline
        except (ValueError, TypeError):
            pass 

        selected_suppliers = request.form.getlist("suppliers[]")
        if selected_suppliers:
            AllowedSupplier.query.filter_by(request_id=rfq.id).delete()
            for uname in selected_suppliers:
                db.session.add(AllowedSupplier(request_id=rfq.id, supplier_username=uname))

        if rfq.status == 'denied':
            rfq.status = 'pending'
            rfq.denial_reason = None
        db.session.commit()
        flash("Η ζήτηση ενημερώθηκε.", "success")
        return redirect(url_for('company_request_detail', req_id=req_id))
    
    current_suppliers = [s.supplier_username for s in rfq.allowed_suppliers]
    suppliers_list = [(u.username, u.display_name) for u in suppliers_all]

    return render_template("edit_request.html", rfq=rfq, suppliers=suppliers_list, current_suppliers=current_suppliers, cost_centers=cost_centers)

@app.route("/chief/requests/<int:req_id>/approve", methods=["POST"])
@require_role("chief")
def chief_approve(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    rfq.status = "open"
    rfq.approved_by = session.get("name")
    rfq.approved_at = datetime.utcnow()
    rfq.denial_reason = None
    db.session.commit()
    flash("Η ζήτηση εγκρίθηκε.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/chief/requests/<int:req_id>/deny", methods=["POST"])
@require_role("chief")
def chief_deny(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    rfq.status = "denied"
    rfq.denial_reason = request.form.get("reason", "No reason provided.")
    db.session.commit()
    flash("Η ζήτηση απορρίφθηκε.", "warning")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/chief/users")
@require_role("chief")
def chief_users():
    users = User.query.all()
    return render_template("chief_users.html", users=users)

@app.route("/chief/users/new", methods=["GET", "POST"])
@require_role("chief")
def chief_user_new():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        role = request.form.get("role")
        display_name = request.form.get("display_name") or username

        if User.query.filter_by(username=username).first():
            flash("Το όνομα χρήστη υπάρχει ήδη.", "danger")
        else:
            u = User(username=username, display_name=display_name, role=role, is_active=True)
            u.set_password(password)
            db.session.add(u)
            if role == 'supplier':
                db.session.flush()
                db.session.add(SupplierProfile(user_id=u.id))
            db.session.commit()
            flash("Ο χρήστης δημιουργήθηκε.", "success")
            return redirect(url_for('chief_users'))
    return render_template("user_new.html")

@app.route("/chief/users/<int:user_id>", methods=["GET", "POST"])
@require_role("chief")
def chief_user_detail(user_id):
    u = User.query.get_or_404(user_id)
    if request.method == "POST":
        u.display_name = request.form.get("display_name")
        u.first_name = request.form.get("first_name")
        u.last_name = request.form.get("last_name")
        u.role = request.form.get("role")
        u.is_active = 'is_active' in request.form
        
        new_pass = request.form.get("password")
        if new_pass:
            u.set_password(new_pass)

        if u.role == 'supplier':
            if not u.profile:
                u.profile = SupplierProfile(user_id=u.id)
            u.profile.company_name = request.form.get("company_name")
            u.profile.tax_id = request.form.get("tax_id")
            u.profile.contact_name = request.form.get("contact_name")
            u.profile.phone = request.form.get("phone")
            u.profile.email = request.form.get("email")
            u.profile.address = request.form.get("address")
            u.profile.city = request.form.get("city")
            u.profile.postal_code = request.form.get("postal_code")
            u.profile.iban = request.form.get("iban")
            u.profile.notes = request.form.get("notes")
            
        db.session.commit()
        flash("Ο χρήστης ενημερώθηκε.", "success")
        return redirect(url_for('chief_users'))
        
    return render_template("chief_user_detail.html", u=u)

@app.route("/chief/cost_centers", methods=["GET", "POST"])
@require_role("chief")
def manage_cost_centers():
    if request.method == "POST":
        code = request.form.get("code").strip()
        name = request.form.get("name").strip()
        
        # Λήψη των νέων πεδίων
        address = (request.form.get("address") or "").strip()
        project_manager = (request.form.get("project_manager") or "").strip()
        receiving_manager = (request.form.get("receiving_manager") or "").strip()
        phone = (request.form.get("phone") or "").strip()

        if code and name:
            if CostCenter.query.filter_by(code=code).first():
                flash("Ο κωδικός έργου υπάρχει ήδη.", "danger")
            else:
                db.session.add(CostCenter(
                    code=code, 
                    name=name,
                    address=address,
                    project_manager=project_manager,
                    receiving_manager=receiving_manager,
                    phone=phone
                ))
                db.session.commit()
                flash("Το έργο προστέθηκε επιτυχώς.", "success")
        else:
            flash("Συμπληρώστε τα υποχρεωτικά πεδία (Κωδικός και Περιγραφή).", "warning")
        return redirect(url_for('manage_cost_centers'))
        
    cost_centers = CostCenter.query.order_by(CostCenter.code.asc()).all()
    return render_template("chief_cost_centers.html", cost_centers=cost_centers)

@app.route("/chief/cost_centers/<int:cc_id>/toggle", methods=["POST"])
@require_role("chief")
def toggle_cost_center(cc_id):
    cc = CostCenter.query.get_or_404(cc_id)
    cc.is_active = not cc.is_active
    db.session.commit()
    flash(f"Το έργο {cc.code} ενημερώθηκε.", "info")
    return redirect(url_for('manage_cost_centers'))

@app.route("/chief/cost_centers/<int:cc_id>/edit", methods=["POST"])
@require_role("chief")
def edit_cost_center(cc_id):
    cc = CostCenter.query.get_or_404(cc_id)
    
    # Διαβάζουμε τα νέα δεδομένα από τη φόρμα
    new_code = request.form.get("code").strip()
    new_name = request.form.get("name").strip()
    
    if not new_code or not new_name:
        flash("Ο κωδικός και η περιγραφή είναι υποχρεωτικά.", "danger")
        return redirect(url_for('manage_cost_centers'))
        
    # Ελέγχουμε μήπως ο νέος κωδικός ανήκει ήδη σε ΑΛΛΟ έργο
    existing = CostCenter.query.filter_by(code=new_code).first()
    if existing and existing.id != cc.id:
        flash("Ο κωδικός έργου χρησιμοποιείται ήδη σε άλλο έργο.", "danger")
        return redirect(url_for('manage_cost_centers'))
        
    # Αποθηκεύουμε τις αλλαγές
    cc.code = new_code
    cc.name = new_name
    cc.address = (request.form.get("address") or "").strip()
    cc.project_manager = (request.form.get("project_manager") or "").strip()
    cc.receiving_manager = (request.form.get("receiving_manager") or "").strip()
    cc.phone = (request.form.get("phone") or "").strip()
    
    db.session.commit()
    flash(f"Το έργο {cc.code} ενημερώθηκε επιτυχώς.", "success")
    return redirect(url_for('manage_cost_centers'))

@app.route("/supplier")
@require_role("supplier")
def supplier_dashboard():
    username = session.get("username")
    rfqs = RequestRFQ.query.filter_by(status="open").join(AllowedSupplier).filter(AllowedSupplier.supplier_username == username).order_by(RequestRFQ.id.desc()).all()
    return render_template("supplier_dash.html", rfqs=rfqs)

@app.route("/supplier/requests/<int:req_id>/bid", methods=["GET", "POST"])
@require_role("supplier")
def supplier_bid(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    supplier_name = session.get("name")
    
    existing_bid = Bid.query.filter_by(request_id=req_id, supplier_name=supplier_name).first()
    is_locked = False
    if existing_bid:
        if ItemAward.query.filter_by(bid_id=existing_bid.id).first():
            is_locked = True
    
    if request.method == "POST":
        if is_locked:
            flash("Η προσφορά έχει κλειδωθεί λόγω ανάθεσης.", "warning")
            return redirect(request.url)

        if not existing_bid:
            existing_bid = Bid(request_id=rfq.id, supplier_name=supplier_name, price=0)
            db.session.add(existing_bid)
            db.session.flush()
        
        BidLine.query.filter_by(bid_id=existing_bid.id).delete()
        
        subtotal = Decimal(0)
        
        for item in rfq.items:
            price_str = request.form.get(f"price_{item.id}")
            if price_str and float(price_str) > 0:
                u_price = Decimal(price_str)
                line_tot = u_price * item.quantity
                
                bl = BidLine(
                    bid_id=existing_bid.id,
                    request_item_id=item.id,
                    description=item.description,
                    unit=item.unit,
                    qty=item.quantity,
                    unit_price=u_price,
                    line_total=line_tot
                )
                db.session.add(bl)
                subtotal += line_tot

        existing_bid.subtotal = subtotal
        shipping = Decimal(request.form.get("shipping", 0))
        vat_pct = Decimal(request.form.get("vat_pct", 24))
        
        vat_amt = (subtotal + shipping) * (vat_pct / 100)
        existing_bid.shipping_cost = shipping
        existing_bid.vat_pct = vat_pct
        existing_bid.vat_amount = vat_amt
        existing_bid.price = subtotal + shipping + vat_amt
        existing_bid.notes = request.form.get("notes")

        db.session.commit()
        flash("Η προσφορά αποθηκεύτηκε.", "success")
        return redirect(url_for('supplier_dashboard'))

    return render_template("supplier_bid.html", rfq=rfq, bid=existing_bid, locked=is_locked)


def _has_column(table: str, column: str) -> bool:
    insp = inspect(db.engine)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols

def migrate_db():
    with db.engine.begin() as conn:
        if not _has_column("users", "first_name"):
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN first_name TEXT")
        if not _has_column("users", "last_name"):
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN last_name TEXT")
        if not _has_column("requests", "approved_by"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN approved_by VARCHAR(100)")
        if not _has_column("requests", "approved_at"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN approved_at DATETIME")
        if not _has_column("requests", "denial_reason"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN denial_reason TEXT")
        if not _has_column("requests", "status"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN status VARCHAR(20)")
            conn.exec_driver_sql("UPDATE requests SET status='open' WHERE status IS NULL")
        if not _has_column("requests", "delivery_location"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN delivery_location VARCHAR(255)")
        if not _has_column("requests", "documents"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN documents VARCHAR(255)")
        if not _has_column("bids", "subtotal"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN subtotal NUMERIC")
        if not _has_column("bids", "discount_total"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN discount_total NUMERIC")
        if not _has_column("bids", "overall_discount_pct"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN overall_discount_pct NUMERIC")
        if not _has_column("bids", "shipping_cost"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN shipping_cost NUMERIC")
        if not _has_column("bids", "vat_pct"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN vat_pct NUMERIC")
        if not _has_column("bids", "vat_amount"):
            conn.exec_driver_sql("ALTER TABLE bids ADD COLUMN vat_amount NUMERIC")
            
        if not _has_column("requests", "cost_center_id"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN cost_center_id INTEGER REFERENCES cost_centers(id)")
        if not _has_column("cost_centers", "address"):
            conn.exec_driver_sql("ALTER TABLE cost_centers ADD COLUMN address VARCHAR(250)")
        if not _has_column("cost_centers", "project_manager"):
            conn.exec_driver_sql("ALTER TABLE cost_centers ADD COLUMN project_manager VARCHAR(120)")
        if not _has_column("cost_centers", "receiving_manager"):
            conn.exec_driver_sql("ALTER TABLE cost_centers ADD COLUMN receiving_manager VARCHAR(120)")
        if not _has_column("cost_centers", "phone"):
            conn.exec_driver_sql("ALTER TABLE cost_centers ADD COLUMN phone VARCHAR(50)")
        if not _has_column("requests", "receiving_manager"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN receiving_manager VARCHAR(120)")
        if not _has_column("requests", "phone"):
            conn.exec_driver_sql("ALTER TABLE requests ADD COLUMN phone VARCHAR(50)")

def init_db():
    with app.app_context():
        def create_user_if_missing(username, password, role, display_name, **kwargs):
            if not User.query.filter_by(username=username).first():
                u = User(username=username, display_name=display_name, role=role, is_active=True, **kwargs)
                u.set_password(password)
                db.session.add(u)
                return u
            return None

        db.create_all()
        migrate_db()
        
        create_user_if_missing("Chief", "Chief", "chief", "Chief")
        create_user_if_missing("Employee", "Employee", "company", "Employee")
        
        for i in range(1, 6):
            uname = f"Προμηθευτής {i}"
            pwd = str(i)
            u = create_user_if_missing(uname, pwd, "supplier", uname)
            if u:
                db.session.flush()
                if not SupplierProfile.query.filter_by(user_id=u.id).first():
                    db.session.add(SupplierProfile(user_id=u.id))
        
        db.session.commit()

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)