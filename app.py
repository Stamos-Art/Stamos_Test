import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for, flash
from sqlalchemy import inspect, or_
from functools import wraps

from models import (
    db, User, SupplierProfile, CostCenter, RequestRFQ, 
    RequestItem, Bid, BidLine, ItemAward, ItemReceipt, AllowedSupplier,
    ActionLog, Notification  # <--- Προστέθηκαν τα νέα models
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

# --- ΣΥΣΤΗΜΑ ΙΣΤΟΡΙΚΟΥ ΚΑΙ ΕΙΔΟΠΟΙΗΣΕΩΝ ---
def log_action(req_id, action_desc):
    if 'name' in session:
        db.session.add(ActionLog(request_id=req_id, user_name=session['name'], action=action_desc))

def notify_user(username, message, link):
    u = User.query.filter_by(username=username).first()
    if u:
        db.session.add(Notification(user_id=u.id, message=message, link=link))

def notify_role(role, message, link):
    users = User.query.filter_by(role=role, is_active=True).all()
    for u in users:
        db.session.add(Notification(user_id=u.id, message=message, link=link))
# ------------------------------------------

def get_phase_key(rfq: "RequestRFQ") -> str:
    if rfq.status == "denied": return "denied"
    if rfq.status == "pending": return "awaiting_approval"
    if rfq.status == "pending_final_approval": return "pending_final_approval"
    if rfq.status == "received": return "received" 
    if rfq.status == "closed": return "awarded"
    if rfq.status == "open":
        count_bids = len(rfq.bids or [])
        return "offers_received" if count_bids > 0 else "awaiting_offers"
    return rfq.status

def phase_info(rfq: "RequestRFQ"):
    key = get_phase_key(rfq)
    mapping = {
        "awaiting_approval": {"label": "Προς Έγκριση", "badge": "badge bg-warning text-dark", "icon": "bi-hourglass-split"},
        "pending_final_approval": {"label": "Αναμονή Τελικής Έγκρισης", "badge": "badge bg-danger", "icon": "bi-shield-lock"},
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
    unread_notifs = []
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            unread_notifs = Notification.query.filter_by(user_id=u.id, is_read=False).order_by(Notification.created_at.desc()).all()
            
    return dict(phase_info=phase_info, is_editable_by_current_user=is_editable_by_current_user, now=datetime.utcnow(), unread_notifs=unread_notifs)

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

# ---- ROUTES ΓΙΑ ΕΙΔΟΠΟΙΗΣΕΙΣ ----
@app.route("/notifications/read/<int:notif_id>")
def read_notification(notif_id):
    n = Notification.query.get_or_404(notif_id)
    if 'username' in session and n.user.username == session['username']:
        n.is_read = True
        db.session.commit()
        return redirect(n.link)
    return redirect(url_for('index'))

@app.route("/notifications/read_all", methods=["POST"])
def read_all_notifications():
    if 'username' in session:
        u = User.query.filter_by(username=session['username']).first()
        if u:
            Notification.query.filter_by(user_id=u.id, is_read=False).update({'is_read': True})
            db.session.commit()
    return redirect(request.referrer or url_for('index'))
# ---------------------------------

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
        r_manager = (request.form.get("receiving_manager") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        details = (request.form.get("details") or "").strip()
        cc_id = request.form.get("cost_center") 
        
        try:
            s_deadline = datetime.strptime(request.form.get("submit_deadline"), "%Y-%m-%d")
            d_deadline = datetime.strptime(request.form.get("delivery_deadline"), "%Y-%m-%d")
        except (ValueError, TypeError):
            flash("Μη έγκυρη ημερομηνία.", "danger")
            return redirect(url_for("new_request"))

        if not cc_id:
            flash("Επίλεξε Έργο/Κέντρο Κόστους.", "danger")
            return redirect(url_for("new_request"))

        rfq = RequestRFQ(
            title=title, description=details, created_by=session.get("name", "Employee"),
            delivery_location=location, receiving_manager=r_manager, phone=phone,                  
            submit_deadline=s_deadline, delivery_deadline=d_deadline, cost_center_id=int(cc_id), status="pending"
        )
        db.session.add(rfq)
        db.session.flush()

        item_descs = request.form.getlist("item_desc[]")
        item_units = request.form.getlist("item_unit[]")
        item_qtys = request.form.getlist("item_qty[]")
        for i in range(len(item_descs)):
            desc = item_descs[i].strip()
            if not desc: continue
            unit = item_units[i] if i < len(item_units) else "τμχ"
            try: qty = float(item_qtys[i])
            except ValueError: qty = 1.0
            db.session.add(RequestItem(request_id=rfq.id, description=desc, unit=unit, quantity=qty))

        selected_suppliers = request.form.getlist("suppliers[]")
        for uname in selected_suppliers:
            db.session.add(AllowedSupplier(request_id=rfq.id, supplier_username=uname))

        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ ΚΑΙ ΕΙΔΟΠΟΙΗΣΗΣ
        log_action(rfq.id, "Δημιουργία νέας ζήτησης (Προσχέδιο).")
        notify_role('chief', f"Νέα ζήτηση #{rfq.id} αναμένει έγκριση.", url_for('company_request_detail', req_id=rfq.id))

        db.session.commit()
        flash("Η ζήτηση δημιουργήθηκε επιτυχώς.", "success")
        return redirect(url_for("company_dashboard"))

    clone_id = request.args.get("clone_id")
    clone_rfq = None
    if clone_id:
        clone_rfq = RequestRFQ.query.get(int(clone_id))

    suppliers_list = [(u.username, u.display_name) for u in suppliers]
    return render_template("new_request.html", suppliers=suppliers_list, cost_centers=cost_centers, clone_rfq=clone_rfq)


@app.route("/company/requests/<int:req_id>")
@require_roles("company", "chief")
def company_request_detail(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    bids = Bid.query.filter_by(request_id=req_id).all()
    
    awards_list = ItemAward.query.filter_by(request_id=req_id).all()
    awards = {aw.request_item_id: aw for aw in awards_list if aw.request_item_id is not None}
    
    shipping_awards = [aw for aw in awards_list if aw.request_item_id is None]
    shipping_winning_bid_ids = {aw.bid_id for aw in shipping_awards}

    awarded_summary = {}
    grand_total_awarded = Decimal(0)
    
    for aw in awards_list:
        sup = aw.supplier_name
        val = aw.line_total or Decimal(0)
        bid = aw.bid
        bl = BidLine.query.get(aw.bid_line_id) if aw.bid_line_id else None
        
        if sup not in awarded_summary:
            effective_disc_pct = Decimal(0)
            if bid and bid.subtotal and bid.subtotal > 0 and bid.discount_total and bid.discount_total > 0:
                effective_disc_pct = bid.discount_total / bid.subtotal
                
            awarded_summary[sup] = {
                'subtotal': Decimal(0), 
                'items': [],
                'effective_disc_pct': effective_disc_pct,
                'overall_discount': Decimal(0),
                'final_total': Decimal(0)
            }
            
        awarded_summary[sup]['subtotal'] += val
        
        if aw.request_item_id is None:
            desc = "Μεταφορικά / Έξοδα Αποστολής"
        else:
            req_item = next((it for it in rfq.items if it.id == aw.request_item_id), None)
            desc = req_item.description if req_item else "Άγνωστο είδος"
            
        item_disc_str = ""
        if bl:
            if bl.discount_type == 'pct' and bl.discount_pct and bl.discount_pct > 0:
                item_disc_str = f"-{bl.discount_pct}%"
            elif bl.discount_type == 'amt' and bl.discount_amount and bl.discount_amount > 0:
                item_disc_str = f"-{bl.discount_amount}€"
                
        awarded_summary[sup]['items'].append({
            'desc': desc, 'qty': aw.qty or Decimal(1), 'price': aw.unit_price or Decimal(0),
            'discount_str': item_disc_str, 'total': val
        })

    for sup, data in awarded_summary.items():
        data['overall_discount'] = data['subtotal'] * data['effective_disc_pct']
        data['final_total'] = data['subtotal'] - data['overall_discount']
        grand_total_awarded += data['final_total']

    receipts_list = ItemReceipt.query.filter_by(request_id=req_id).all()
    receipts = {r.request_item_id: r for r in receipts_list}

    return render_template("company_request_detail.html", 
                           rfq=rfq, items=rfq.items, bids=bids, awards=awards, 
                           shipping_awards=shipping_awards, shipping_winning_bid_ids=shipping_winning_bid_ids,
                           awarded_summary=awarded_summary, grand_total_awarded=grand_total_awarded, receipts=receipts)


@app.route("/company/requests/<int:req_id>/save_receipt", methods=["POST"])
@require_roles("company", "chief")
def save_receipt(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    if rfq.status not in ['closed', 'received']:
        flash("Μη έγκυρη ενέργεια.", "danger")
        return redirect(url_for('company_request_detail', req_id=req_id))
        
    for item in rfq.items:
        recv_qty_str = request.form.get(f"recv_qty_{item.id}")
        if recv_qty_str and recv_qty_str.strip():
            try:
                qty = Decimal(recv_qty_str.strip())
                receipt = ItemReceipt.query.filter_by(request_id=rfq.id, request_item_id=item.id).first()
                if not receipt:
                    award = ItemAward.query.filter_by(request_id=rfq.id, request_item_id=item.id).first()
                    supplier = award.supplier_name if award else "Άγνωστος"
                    receipt = ItemReceipt(request_id=rfq.id, request_item_id=item.id, awarded_supplier=supplier)
                    db.session.add(receipt)
                
                receipt.received_qty = qty
                receipt.received_by = session.get("name")
                receipt.received_at = datetime.utcnow()
            except Exception:
                pass
    
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
    log_action(rfq.id, "Ενημέρωση ποσοτήτων παραλαβής ειδών.")
    db.session.commit()
    flash("Οι ποσότητες παραλαβής αποθηκεύτηκαν επιτυχώς.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/company/requests/<int:req_id>/finalize_receipt", methods=["POST"])
@require_roles("company", "chief")
def finalize_receipt(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    rfq.status = 'received'
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
    log_action(rfq.id, "Οριστική ολοκλήρωση παραλαβής.")
    db.session.commit()
    flash("Η παραλαβή ολοκληρώθηκε οριστικά!", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/company/requests/<int:req_id>/award_item", methods=["POST"])
@require_roles("company", "chief")
def award_item(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    if rfq.status == 'closed' or (rfq.status == 'pending_final_approval' and session.get('role') != 'chief'):
        flash("Δεν μπορείτε να τροποποιήσετε τις αναθέσεις σε αυτή την κατάσταση.", "danger")
        return redirect(url_for('company_request_detail', req_id=req_id))

    item_id_raw = request.form.get("request_item_id")
    bid_line_id = request.form.get("bid_line_id")
    bid_line = BidLine.query.get(bid_line_id)

    supplier_name = bid_line.bid.supplier_name

    if item_id_raw == 'shipping':
        award = ItemAward.query.filter_by(request_id=req_id, request_item_id=None, bid_id=bid_line.bid_id).first()
        if not award: award = ItemAward(request_id=req_id, request_item_id=None)
    else:
        item_id = int(item_id_raw)
        award = ItemAward.query.filter_by(request_id=req_id, request_item_id=item_id).first()
        if not award: award = ItemAward(request_id=req_id, request_item_id=item_id)

    award.bid_id = bid_line.bid_id
    award.bid_line_id = bid_line.id
    award.supplier_name = supplier_name
    award.line_total = bid_line.line_total
    award.qty = bid_line.qty
    award.unit_price = bid_line.unit_price
    
    db.session.add(award)
    
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
    log_action(rfq.id, f"Ανάθεση '{bid_line.description}' στον προμηθευτή '{supplier_name}'.")
    
    db.session.commit()
    flash(f"Η ανάθεση για '{bid_line.description}' ενημερώθηκε.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id, open_bid=bid_line.bid_id))

@app.route("/company/requests/<int:req_id>/unaward_item", methods=["POST"])
@require_roles("company", "chief")
def unaward_item(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    if rfq.status == 'closed' or (rfq.status == 'pending_final_approval' and session.get('role') != 'chief'):
        flash("Δεν μπορείτε να τροποποιήσετε τις αναθέσεις σε αυτή την κατάσταση.", "danger")
        return redirect(url_for('company_request_detail', req_id=req_id))

    item_id_raw = request.form.get("request_item_id")
    bid_id = request.form.get("bid_id") 

    if item_id_raw == 'shipping':
        award = ItemAward.query.filter_by(request_id=req_id, request_item_id=None, bid_id=bid_id).first()
    else:
        award = ItemAward.query.filter_by(request_id=req_id, request_item_id=int(item_id_raw)).first()
    
    if award:
        db.session.delete(award)
        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
        log_action(rfq.id, "Ακύρωση ανάθεσης είδους.")
        db.session.commit()
        flash("Η ανάθεση ακυρώθηκε.", "info")
    return redirect(url_for('company_request_detail', req_id=req_id, open_bid=bid_id))

@app.route("/company/requests/<int:req_id>/finalize_award", methods=["POST"])
@require_roles("company", "chief")
def finalize_award(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    awards_list = ItemAward.query.filter_by(request_id=rfq.id).all()
    
    if not awards_list:
        flash("Δεν έχετε επιλέξει κανένα είδος για ανάθεση.", "warning")
        return redirect(url_for('company_request_detail', req_id=req_id))

    awarded_summary = {}
    grand_total_awarded = Decimal(0)
    for aw in awards_list:
        sup = aw.supplier_name
        val = aw.line_total or Decimal(0)
        bid = aw.bid
        
        if sup not in awarded_summary:
            effective_disc_pct = Decimal(0)
            if bid and bid.subtotal and bid.subtotal > 0 and bid.discount_total and bid.discount_total > 0:
                effective_disc_pct = bid.discount_total / bid.subtotal
            awarded_summary[sup] = {'subtotal': Decimal(0), 'effective_disc_pct': effective_disc_pct}
            
        awarded_summary[sup]['subtotal'] += val

    for sup, data in awarded_summary.items():
        overall_discount = data['subtotal'] * data['effective_disc_pct']
        final_total = data['subtotal'] - overall_discount
        grand_total_awarded += final_total

    if grand_total_awarded > 500 and session.get('role') == 'company':
        rfq.status = 'pending_final_approval'
        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ & ΕΙΔΟΠΟΙΗΣΗΣ
        log_action(rfq.id, f"Αναμονή τελικής έγκρισης από Διευθυντή (Σύνολο: {grand_total_awarded:.2f}€).")
        notify_role('chief', f"Η ζήτηση #{rfq.id} υπερβαίνει τα 500€ και απαιτεί τελική έγκριση.", url_for('company_request_detail', req_id=rfq.id))
        
        db.session.commit()
        flash(f"Το συνολικό κόστος ({grand_total_awarded:.2f}€) υπερβαίνει τα 500€. Εστάλη στον Διευθυντή για τελική έγκριση.", "info")
    else:
        rfq.status = 'closed'
        
        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ & ΕΙΔΟΠΟΙΗΣΗΣ ΣΤΟΥΣ ΠΡΟΜΗΘΕΥΤΕΣ
        log_action(rfq.id, "Οριστική κατακύρωση παραγγελίας στους προμηθευτές.")
        winners = {aw.supplier_name for aw in awards_list}
        for w in winners:
            u = User.query.filter_by(display_name=w).first()
            if u: notify_user(u.username, f"Συγχαρητήρια! Σας ανατέθηκε η παραγγελία #{rfq.id}.", url_for('supplier_bid', req_id=rfq.id))
            
        db.session.commit()
        flash(f"Η ανάθεση οριστικοποιήθηκε. Η ζήτηση έκλεισε επιτυχώς!", "success")
        
    return redirect(url_for('company_dashboard'))

@app.route("/company/requests/<int:req_id>/revert_approval", methods=["POST"])
@require_roles("chief")
def revert_approval(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    rfq.status = 'open'
    
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ & ΕΙΔΟΠΟΙΗΣΗΣ
    log_action(rfq.id, "Ο Διευθυντής επέστρεψε τη ζήτηση στον υπάλληλο.")
    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u: notify_user(u.username, f"Η ζήτηση #{rfq.id} σας επιστράφηκε για επανεξέταση.", url_for('company_request_detail', req_id=rfq.id))
        
    db.session.commit()
    flash("Η ζήτηση επιστράφηκε στον υπάλληλο για επανεξέταση.", "warning")
    return redirect(url_for('company_request_detail', req_id=req_id))


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

        RequestItem.query.filter_by(request_id=rfq.id).delete()
        item_descs = request.form.getlist("item_desc[]")
        item_units = request.form.getlist("item_unit[]")
        item_qtys = request.form.getlist("item_qty[]")
        for i in range(len(item_descs)):
            desc = item_descs[i].strip()
            if not desc:
                continue
            unit = item_units[i] if i < len(item_units) else "τμχ"
            try:
                qty = float(item_qtys[i])
            except ValueError:
                qty = 1.0
            db.session.add(RequestItem(request_id=rfq.id, description=desc, unit=unit, quantity=qty))

        if rfq.status == 'denied':
            rfq.status = 'pending'
            rfq.denial_reason = None
            
        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
        log_action(rfq.id, "Επεξεργασία στοιχείων ζήτησης.")
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
    
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ & ΕΙΔΟΠΟΙΗΣΗΣ
    log_action(rfq.id, "Έγκριση και Δημοσίευση στους προμηθευτές.")
    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u: notify_user(u.username, f"Η ζήτηση #{rfq.id} εγκρίθηκε και δημοσιεύτηκε.", url_for('company_request_detail', req_id=rfq.id))
        
    db.session.commit()
    flash("Η ζήτηση εγκρίθηκε.", "success")
    return redirect(url_for('company_request_detail', req_id=req_id))

@app.route("/chief/requests/<int:req_id>/deny", methods=["POST"])
@require_role("chief")
def chief_deny(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    rfq.status = "denied"
    reason = request.form.get("reason", "No reason provided.")
    rfq.denial_reason = reason
    
    # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ & ΕΙΔΟΠΟΙΗΣΗΣ
    log_action(rfq.id, f"Απόρριψη ζήτησης. Λόγος: {reason}")
    u = User.query.filter_by(display_name=rfq.created_by).first()
    if u: notify_user(u.username, f"Η ζήτηση #{rfq.id} απορρίφθηκε.", url_for('company_request_detail', req_id=rfq.id))
        
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
    
    new_code = request.form.get("code").strip()
    new_name = request.form.get("name").strip()
    
    if not new_code or not new_name:
        flash("Ο κωδικός και η περιγραφή είναι υποχρεωτικά.", "danger")
        return redirect(url_for('manage_cost_centers'))
        
    existing = CostCenter.query.filter_by(code=new_code).first()
    if existing and existing.id != cc.id:
        flash("Ο κωδικός έργου χρησιμοποιείται ήδη σε άλλο έργο.", "danger")
        return redirect(url_for('manage_cost_centers'))
        
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
    supplier_name = session.get("name")
    
    rfqs = RequestRFQ.query.filter_by(status="open").join(AllowedSupplier).filter(AllowedSupplier.supplier_username == username).all()
    
    bids = Bid.query.filter_by(supplier_name=supplier_name).all()
    bids_map = {b.request_id: b for b in bids}
    
    submitted_count = Bid.query.filter_by(supplier_name=supplier_name, status='submitted').count()
    
    awards_count = ItemAward.query.join(RequestRFQ).filter(
        ItemAward.supplier_name == supplier_name,
        RequestRFQ.status.in_(['closed', 'received'])
    ).count()
    
    awarded_awards = ItemAward.query.join(RequestRFQ).filter(
        ItemAward.supplier_name == supplier_name,
        RequestRFQ.status.in_(['closed', 'received'])
    ).all()
    
    awarded_rfqs = list({RequestRFQ.query.get(aw.request_id) for aw in awarded_awards})
    awarded_rfqs.sort(key=lambda x: x.id, reverse=True)
    
    pending_count = len(rfqs) - submitted_count

    return render_template("supplier_dash.html", 
                           rfqs=rfqs, 
                           awarded_rfqs=awarded_rfqs,
                           bids_map=bids_map,
                           pending_count=max(0, pending_count),
                           submitted_count=submitted_count,
                           awards_count=awards_count)


@app.route("/supplier/history")
@require_role("supplier")
def supplier_history():
    supplier_name = session.get("name")
    my_bids = Bid.query.filter_by(supplier_name=supplier_name).order_by(Bid.created_at.desc()).all()
    return render_template("supplier_history.html", bids=my_bids)

@app.route("/supplier/requests/<int:req_id>/bid", methods=["GET", "POST"])
@require_role("supplier")
def supplier_bid(req_id):
    rfq = RequestRFQ.query.get_or_404(req_id)
    supplier_name = session.get("name")
    username = session.get("username")
    
    current_user = User.query.filter_by(username=username).first()
    existing_bid = Bid.query.filter_by(request_id=req_id, supplier_id=current_user.id).first()
    
    is_rfq_closed = rfq.status in ['closed', 'received']
    
    is_locked = False
    if is_rfq_closed or (existing_bid and ItemAward.query.filter_by(bid_id=existing_bid.id).first()):
        is_locked = True

    if request.method == "POST":
        if is_locked:
            flash("Η προσφορά είναι κλειδωμένη λόγω ανάθεσης.", "danger")
            return redirect(url_for('supplier_dashboard'))

        action = request.form.get("action")
        
        if not existing_bid:
            existing_bid = Bid(request_id=rfq.id, supplier_id=current_user.id, supplier_name=supplier_name, price=0)
            db.session.add(existing_bid)
            db.session.flush()
        
        BidLine.query.filter_by(bid_id=existing_bid.id).delete()
        
        subtotal = Decimal(0)
        total_vat = Decimal(0)

        for item in rfq.items:
            price = Decimal(request.form.get(f"item_price_{item.id}") or 0)
            disc_val = Decimal(request.form.get(f"item_discount_{item.id}") or 0)
            disc_type = request.form.get(f"item_discount_type_{item.id}") or 'pct'
            vat_p = Decimal(request.form.get(f"item_vat_{item.id}") or 24)
            
            line_gross = price * Decimal(item.quantity)
            line_net = line_gross * (1 - disc_val/100) if disc_type == 'pct' else max(0, line_gross - disc_val)
            
            bl = BidLine(
                bid_id=existing_bid.id, request_item_id=item.id,
                description=item.description, unit=item.unit, qty=item.quantity,
                unit_price=price, discount_pct=disc_val if disc_type == 'pct' else 0,
                discount_amount=disc_val if disc_type == 'amt' else 0,
                discount_type=disc_type, vat_pct=vat_p, line_total=line_net, is_combo=False
            )
            db.session.add(bl)
            subtotal += line_net
            total_vat += (line_net * vat_p / 100)

        ship_price = Decimal(request.form.get("shipping_cost") or 0)
        if ship_price > 0:
            ship_line = BidLine(
                bid_id=existing_bid.id, description="Μεταφορικά / Έξοδα Αποστολής",
                qty=1, unit="υπηρεσία", unit_price=ship_price, line_total=ship_price,
                vat_pct=24, is_combo=True 
            )
            db.session.add(ship_line)
            subtotal += ship_price
            total_vat += (ship_price * Decimal(0.24))

        ov_disc = Decimal(request.form.get("overall_discount_val") or 0)
        ov_type = request.form.get("overall_discount_type") or 'pct'
        final_disc = (subtotal * ov_disc / 100) if ov_type == 'pct' else ov_disc
        
        existing_bid.subtotal = subtotal
        existing_bid.discount_total = final_disc
        existing_bid.overall_discount_type = ov_type
        existing_bid.vat_amount = total_vat
        existing_bid.price = subtotal - final_disc + total_vat
        existing_bid.status = 'submitted' if action == 'submit' else 'draft'
        
        existing_bid.shipping_cost = ship_price
        existing_bid.notes = request.form.get("notes")
        
        prop_date = request.form.get("proposed_delivery_date")
        if prop_date:
            try:
                existing_bid.proposed_delivery_date = datetime.strptime(prop_date, "%Y-%m-%d")
            except ValueError:
                pass

        # --> ΠΡΟΣΘΗΚΗ ΙΣΤΟΡΙΚΟΥ
        log_action(rfq.id, f"Ο προμηθευτής '{supplier_name}' {'υπέβαλε' if action == 'submit' else 'αποθήκευσε'} προσφορά.")
        db.session.commit()
        flash("Επιτυχής αποθήκευση προσφοράς.", "success")
        return redirect(url_for('supplier_dashboard'))
    
    item_prefill = {}
    if existing_bid:
        for bl in existing_bid.lines:
            if not bl.is_combo:
                item_prefill[bl.request_item_id] = {
                    'price': bl.unit_price, 
                    'disc': bl.discount_pct if bl.discount_type == 'pct' else bl.discount_amount,
                    'disc_type': bl.discount_type,
                    'vat': bl.vat_pct
                }

    my_awards = []
    my_awards_total = Decimal(0)
    overall_discount_amount = Decimal(0)
    final_award_total = Decimal(0)
    receipts = {}  # ΝΕΟ: Λεξικό για τις παραλαβές
    
    if is_rfq_closed and existing_bid:
        my_awards = ItemAward.query.filter_by(request_id=req_id, bid_id=existing_bid.id).all()
        for aw in my_awards:
            my_awards_total += (aw.line_total or Decimal(0))
            
        effective_disc_pct = Decimal(0)
        if existing_bid.subtotal and existing_bid.subtotal > 0 and existing_bid.discount_total and existing_bid.discount_total > 0:
            effective_disc_pct = existing_bid.discount_total / existing_bid.subtotal
            
        overall_discount_amount = my_awards_total * effective_disc_pct
        final_award_total = my_awards_total - overall_discount_amount

        # ΝΕΟ: Ανάκτηση των παραλαβών για να τις δει ο Προμηθευτής
        receipts_list = ItemReceipt.query.filter_by(request_id=req_id).all()
        receipts = {r.request_item_id: r for r in receipts_list}

    return render_template("supplier_bid.html", 
                           rfq=rfq, bid=existing_bid, readonly=is_locked,
                           item_prefill=item_prefill,
                           overall_prefill=existing_bid.overall_discount_pct if existing_bid and existing_bid.overall_discount_type == 'pct' else (existing_bid.discount_total if existing_bid else 0),
                           discount_type=existing_bid.overall_discount_type if existing_bid else 'pct',
                           shipping_prefill=existing_bid.shipping_cost if existing_bid else 0,
                           my_awards=my_awards,
                           my_awards_total=my_awards_total,
                           overall_discount_amount=overall_discount_amount,
                           final_award_total=final_award_total,
                           is_rfq_closed=is_rfq_closed,
                           receipts=receipts)

def _has_column(table: str, column: str) -> bool:
    insp = inspect(db.engine)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols

def migrate_db():
    with db.engine.begin() as conn:
        pass # Απλά επιτρέπουμε να τρέξει χωρίς SQL edits γιατί το create_all πιάνει τα νέα Tables

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