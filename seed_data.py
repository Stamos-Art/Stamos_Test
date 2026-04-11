"""
seed_data.py – Ρεαλιστικά δεδομένα δοκιμής για το ProcureApp.

Εκτέλεση:
    python seed_data.py

Το script:
  • Διαγράφει τα υπάρχοντα δεδομένα (εκτός αν θέλετε να τα κρατήσετε).
  • Δημιουργεί χρήστες, κέντρα κόστους, ζητήσεις σε ΟΛΕς τις καταστάσεις,
    προσφορές, αναθέσεις και παραλαβές.

Διαπιστευτήρια μετά το seed:
  ┌─────────────────────┬──────────────┬────────────┐
  │ Username            │ Password     │ Ρόλος      │
  ├─────────────────────┼──────────────┼────────────┤
  │ nikos.papadopoulos  │ Chief123!    │ chief      │
  │ maria.georgiou      │ Company123!  │ company    │
  │ kostas.antoniou     │ Company123!  │ company    │
  │ techniki_oe         │ Supplier1!   │ supplier   │
  │ hellas_constructions│ Supplier2!   │ supplier   │
  │ proio_supply        │ Supplier3!   │ supplier   │
  │ office_world        │ Supplier4!   │ supplier   │
  │ green_clean         │ Supplier5!   │ supplier   │
  └─────────────────────┴──────────────┴────────────┘
"""

import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# ── Ensure the app module is importable ──────────────────────────────────────
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from app import app, db
from models import (
    User, SupplierProfile, CostCenter, RequestRFQ,
    RequestItem, Bid, BidLine, ItemAward, ItemReceipt,
    AllowedSupplier, ActionLog, Notification, RFQStatus
)

# ── Helpers ──────────────────────────────────────────────────────────────────
def ago(days=0, hours=0):
    return datetime.utcnow() - timedelta(days=days, hours=hours)


def make_user(username, password, role, display_name, first_name="", last_name="",
              approval_limit=None):
    u = User.query.filter_by(username=username).first()
    if not u:
        u = User(username=username, display_name=display_name, role=role,
                 is_active=True, first_name=first_name, last_name=last_name)
    u.set_password(password)
    if approval_limit is not None:
        u.approval_limit = Decimal(str(approval_limit))
    db.session.add(u)
    db.session.flush()
    return u


# ── Main seed function ────────────────────────────────────────────────────────
def seed():
    with app.app_context():
        # ── 0. Wipe existing data (safe order to respect FK constraints) ──────
        print("🗑  Καθαρισμός παλαιών δεδομένων …")
        for model in [Notification, ActionLog, ItemReceipt, ItemAward,
                      BidLine, Bid, AllowedSupplier, RequestItem,
                      RequestRFQ, SupplierProfile, CostCenter, User]:
            model.query.delete()
        db.session.commit()

        # ── 1. Users ──────────────────────────────────────────────────────────
        print("👤 Δημιουργία χρηστών …")

        chief = make_user("nikos.papadopoulos", "Chief123!", "chief",
                          "Νίκος Παπαδόπουλος", "Νίκος", "Παπαδόπουλος",
                          approval_limit=999999)

        emp1 = make_user("maria.georgiou", "Company123!", "company",
                         "Μαρία Γεωργίου", "Μαρία", "Γεωργίου",
                         approval_limit=2000)

        emp2 = make_user("kostas.antoniou", "Company123!", "company",
                         "Κώστας Αντωνίου", "Κώστας", "Αντωνίου",
                         approval_limit=500)

        sup_data = [
            ("techniki_oe",          "Supplier1!", "Τεχνική Ο.Ε.",
             "ΤΕΧΝΙΚΗ Ο.Ε.", "010203040",
             "Δημήτρης Λαζαρίδης", "+30 210 1234567",
             "info@techniki-oe.gr", "Λεωφόρος Αθηνών 45", "Αθήνα", "10441",
             "GR1601101250000000012300695"),

            ("hellas_constructions",  "Supplier2!", "Hellas Constructions Α.Ε.",
             "HELLAS CONSTRUCTIONS Α.Ε.", "020304050",
             "Σοφία Κωστοπούλου", "+30 2310 987654",
             "orders@hellas-con.gr", "Εγνατία 112", "Θεσσαλονίκη", "54626",
             "GR2701101250000000023456789"),

            ("proio_supply",          "Supplier3!", "Πρώιο Εφοδιασμός Ε.Π.Ε.",
             "ΠΡΩΙΟ ΕΦΟΔΙΑΣΜΟΣ Ε.Π.Ε.", "030405060",
             "Γιάννης Πρώιος", "+30 2610 223344",
             "sales@proio.gr", "Κορίνθου 8", "Πάτρα", "26221",
             "GR3301101250000000034567890"),

            ("office_world",          "Supplier4!", "Office World Α.Β.Ε.Ε.",
             "OFFICE WORLD Α.Β.Ε.Ε.", "040506070",
             "Άννα Χατζή", "+30 210 6543210",
             "b2b@officeworld.gr", "Κηφισίας 200", "Αθήνα", "15231",
             "GR4401101250000000045678901"),

            ("green_clean",           "Supplier5!", "Green Clean Υπηρεσίες Καθαρισμού",
             "GREEN CLEAN ΙΚΕ", "050607080",
             "Ελένη Δήμου", "+30 210 9876543",
             "contact@greenclean.gr", "Πειραιώς 300", "Πειραιάς", "18544",
             "GR5501101250000000056789012"),
        ]

        suppliers = []
        for (uname, pwd, disp, company, tax, contact, phone,
             email, addr, city, postal, iban) in sup_data:
            u = make_user(uname, pwd, "supplier", disp)
            profile = SupplierProfile(
                user_id=u.id, company_name=company, tax_id=tax,
                contact_name=contact, phone=phone, email=email,
                address=addr, city=city, postal_code=postal, iban=iban
            )
            db.session.add(profile)
            suppliers.append(u)

        db.session.flush()

        # ── 2. Cost Centers ───────────────────────────────────────────────────
        print("🏗  Δημιουργία Κέντρων Κόστους …")

        cc_data = [
            ("CC-001", "Ανακαίνιση Γραφείων Αθηνών",
             "Λεωφόρος Κηφισίας 50, Μαρούσι", "Νίκος Παπαδόπουλος",
             "Μαρία Γεωργίου", "+30 210 1111111"),
            ("CC-002", "Κατασκευή Αποθήκης Πειραιά",
             "Λιμενική Ζώνη 15, Πειραιάς", "Νίκος Παπαδόπουλος",
             "Κώστας Αντωνίου", "+30 210 2222222"),
            ("CC-003", "Εξοπλισμός Υποκαταστήματος Θεσσαλονίκης",
             "Εγνατία 200, Θεσσαλονίκη", "Νίκος Παπαδόπουλος",
             "Μαρία Γεωργίου", "+30 2310 333333"),
            ("CC-004", "Συντήρηση Εγκαταστάσεων 2026",
             "Κεντρικά Γραφεία", "Νίκος Παπαδόπουλος",
             "Κώστας Αντωνίου", "+30 210 4444444"),
            ("CC-005", "Αναβάθμιση IT Υποδομής",
             "Κεντρικά Γραφεία", "Νίκος Παπαδόπουλος",
             "Μαρία Γεωργίου", "+30 210 5555555"),
        ]

        ccs = []
        for (code, name, addr, pm, rm, phone) in cc_data:
            cc = CostCenter(code=code, name=name, address=addr,
                            project_manager=pm, receiving_manager=rm,
                            phone=phone, is_active=True)
            db.session.add(cc)
            ccs.append(cc)
        db.session.flush()

        # ── 3. Helper: quick log / notify ─────────────────────────────────────
        def log(rfq, user_display, action):
            db.session.add(ActionLog(request_id=rfq.id,
                                     user_name=user_display, action=action))

        def notif(user_obj, msg, link):
            db.session.add(Notification(user_id=user_obj.id,
                                        message=msg, link=link))

        # ── 4. RFQ helpers ────────────────────────────────────────────────────
        def make_rfq(title, description, created_by_name, cc, status,
                     items_data, allowed_sup_usernames,
                     submit_days_from_now=7, delivery_days_from_now=30,
                     created_days_ago=5, approved_by=None, approved_days_ago=None,
                     denial_reason=None, documents=None):
            rfq = RequestRFQ(
                title=title,
                description=description,
                created_by=created_by_name,
                cost_center_id=cc.id,
                status=status,
                submit_deadline=ago(-submit_days_from_now),
                delivery_deadline=ago(-delivery_days_from_now),
                created_at=ago(created_days_ago),
                documents=documents,
                delivery_location=cc.address,
                receiving_manager=cc.receiving_manager,
                phone=cc.phone,
            )
            if approved_by:
                rfq.approved_by = approved_by
                rfq.approved_at = ago(approved_days_ago or 0)
            if denial_reason:
                rfq.denial_reason = denial_reason
            db.session.add(rfq)
            db.session.flush()

            for (desc, unit, qty) in items_data:
                db.session.add(RequestItem(
                    request_id=rfq.id, description=desc, unit=unit, quantity=qty))
            db.session.flush()

            for uname in allowed_sup_usernames:
                db.session.add(AllowedSupplier(
                    request_id=rfq.id, supplier_username=uname))
            db.session.flush()
            return rfq

        def make_bid(rfq, supplier_user, lines_data, shipping=Decimal("0"),
                     overall_disc_pct=Decimal("0"), notes="",
                     status="submitted", days_ago=3,
                     proposed_delivery_days=14):
            """
            lines_data: list of (request_item, unit_price, disc_pct, vat_pct)
            """
            subtotal = Decimal("0")
            total_vat = Decimal("0")

            bid = Bid(
                request_id=rfq.id,
                supplier_id=supplier_user.id,
                supplier_name=supplier_user.display_name,
                price=0, status=status,
                overall_discount_type="pct",
                overall_discount_pct=overall_disc_pct,
                shipping_cost=shipping,
                notes=notes,
                created_at=ago(days_ago),
                proposed_delivery_date=ago(-proposed_delivery_days),
            )
            db.session.add(bid)
            db.session.flush()

            for (item, unit_price, disc_pct, vat_pct) in lines_data:
                unit_price = Decimal(str(unit_price))
                disc_pct = Decimal(str(disc_pct))
                vat_pct = Decimal(str(vat_pct))
                line_gross = unit_price * Decimal(str(item.quantity))
                disc_amount = line_gross * disc_pct / 100
                line_net = line_gross - disc_amount
                vat_amount = line_net * vat_pct / 100

                db.session.add(BidLine(
                    bid_id=bid.id,
                    request_item_id=item.id,
                    description=item.description,
                    unit=item.unit,
                    qty=item.quantity,
                    unit_price=unit_price,
                    discount_pct=disc_pct,
                    discount_amount=disc_amount,
                    discount_type="pct",
                    line_total=line_net,
                    vat_pct=vat_pct,
                    is_combo=False,
                ))
                subtotal += line_net
                total_vat += vat_amount

            if shipping > 0:
                ship_vat = shipping * Decimal("0.24")
                db.session.add(BidLine(
                    bid_id=bid.id,
                    description="Μεταφορικά / Έξοδα Αποστολής",
                    qty=1, unit="υπηρεσία",
                    unit_price=shipping,
                    discount_pct=0, discount_amount=0,
                    discount_type="pct",
                    line_total=shipping,
                    vat_pct=24,
                    is_combo=True,
                ))
                subtotal += shipping
                total_vat += ship_vat

            final_disc = subtotal * overall_disc_pct / 100
            bid.subtotal = subtotal
            bid.discount_total = final_disc
            bid.vat_amount = total_vat
            bid.price = subtotal - final_disc + total_vat
            db.session.flush()
            return bid

        def award_all(rfq, bid):
            """Award every line of a bid to its items."""
            for bl in bid.lines:
                if bl.is_combo:
                    # shipping line
                    aw = ItemAward(
                        request_id=rfq.id,
                        request_item_id=None,
                        bid_id=bid.id,
                        bid_line_id=bl.id,
                        supplier_name=bid.supplier_name,
                        qty=bl.qty,
                        unit_price=bl.unit_price,
                        line_total=bl.line_total,
                    )
                else:
                    aw = ItemAward(
                        request_id=rfq.id,
                        request_item_id=bl.request_item_id,
                        bid_id=bid.id,
                        bid_line_id=bl.id,
                        supplier_name=bid.supplier_name,
                        qty=bl.qty,
                        unit_price=bl.unit_price,
                        line_total=bl.line_total,
                    )
                db.session.add(aw)
            db.session.flush()

        def receive_all(rfq):
            """Mark all items as fully received."""
            for item in rfq.items:
                aw = ItemAward.query.filter_by(
                    request_id=rfq.id, request_item_id=item.id).first()
                if aw:
                    db.session.add(ItemReceipt(
                        request_id=rfq.id,
                        request_item_id=item.id,
                        awarded_supplier=aw.supplier_name,
                        received_qty=item.quantity,
                        received_by=rfq.receiving_manager or "Αρμόδιος",
                        received_at=ago(1),
                    ))
            db.session.flush()

        # ─────────────────────────────────────────────────────────────────────
        # ── 5. RFQ #1 – PENDING (αναμένει έγκριση από Chief) ─────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #1 – PENDING …")
        rfq1 = make_rfq(
            title="Προμήθεια Γραφικής Ύλης & Αναλωσίμων Γραφείου",
            description=(
                "Απαιτείται η προμήθεια γραφικής ύλης και αναλωσίμων "
                "για τις ανάγκες των κεντρικών γραφείων για το Β' Τρίμηνο 2026. "
                "Παρακαλείστε να υποβάλετε αναλυτική προσφορά."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[0], status=RFQStatus.PENDING,
            items_data=[
                ("Χαρτί Α4 80gr (δεσμίδα 500 φ.)", "δεσμίδα", 50),
                ("Στυλό Ballpoint μπλε (κουτί 50τμχ)", "κουτί", 10),
                ("Ταινία Διαφανής 19mm×33m", "τεμ.", 30),
                ("Αρχειοθήκη Α4 Πλαστική", "τεμ.", 20),
                ("Μαρκαδόρος Ανεξίτηλος (σετ 4 χρωμάτων)", "σετ", 15),
            ],
            allowed_sup_usernames=["office_world", "proio_supply"],
            submit_days_from_now=10, delivery_days_from_now=25,
            created_days_ago=2,
        )
        log(rfq1, emp1.display_name, "Δημιουργία νέας ζήτησης (Προσχέδιο).")
        notif(chief, f"Νέα ζήτηση #{rfq1.id} αναμένει έγκριση.",
              f"/company/requests/{rfq1.id}")

        # ─────────────────────────────────────────────────────────────────────
        # ── 6. RFQ #2 – OPEN, χωρίς προσφορές ────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #2 – OPEN (αναμονή προσφορών) …")
        rfq2 = make_rfq(
            title="Εργασίες Ηλεκτρολογικής Συντήρησης – Αθήνα",
            description=(
                "Ζητούνται εργασίες ετήσιας συντήρησης ηλεκτρολογικών "
                "εγκαταστάσεων στα κεντρικά γραφεία (3 ορόφους). "
                "Απαιτείται πιστοποίηση ηλεκτρολόγου Δ' ειδικότητας."
            ),
            created_by_name=emp2.display_name,
            cc=ccs[3], status=RFQStatus.OPEN,
            items_data=[
                ("Έλεγχος & συντήρηση πίνακα διανομής Ισογείου", "εργασία", 1),
                ("Έλεγχος & συντήρηση πίνακα διανομής 1ου ορόφου", "εργασία", 1),
                ("Αντικατάσταση ασφαλειών & διακοπτών", "τεμ.", 12),
                ("Μέτρηση γείωσης & έκδοση βεβαίωσης", "εργασία", 1),
            ],
            allowed_sup_usernames=["techniki_oe", "hellas_constructions"],
            submit_days_from_now=14, delivery_days_from_now=45,
            created_days_ago=4,
            approved_by=chief.display_name, approved_days_ago=3,
        )
        log(rfq2, emp2.display_name, "Δημιουργία νέας ζήτησης.")
        log(rfq2, chief.display_name, "Έγκριση και δημοσίευση στους προμηθευτές.")

        # ─────────────────────────────────────────────────────────────────────
        # ── 7. RFQ #3 – OPEN με προσφορές ────────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #3 – OPEN (με προσφορές) …")
        rfq3 = make_rfq(
            title="Προμήθεια Εξοπλισμού Γραφείου (Έπιπλα)",
            description=(
                "Αγορά νέων επίπλων γραφείου για τη νέα πτέρυγα του "
                "υποκαταστήματος Θεσσαλονίκης. Απαιτείται παράδοση & "
                "τοποθέτηση επί τόπου."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[2], status=RFQStatus.OPEN,
            items_data=[
                ("Γραφείο εργασίας 160×80 cm (λευκό/γκρι)", "τεμ.", 8),
                ("Καρέκλα εργονομική με ρυθμιζόμενα μπράτσα", "τεμ.", 8),
                ("Βιβλιοθήκη 5 ραφιών 80×30×200 cm", "τεμ.", 4),
                ("Κλειδωτό συρταρατζάντα 3 συρταριών", "τεμ.", 8),
                ("Τραπέζι συσκέψεων 200×100 cm", "τεμ.", 1),
            ],
            allowed_sup_usernames=["office_world", "proio_supply", "hellas_constructions"],
            submit_days_from_now=5, delivery_days_from_now=60,
            created_days_ago=10,
            approved_by=chief.display_name, approved_days_ago=8,
        )
        log(rfq3, emp1.display_name, "Δημιουργία νέας ζήτησης.")
        log(rfq3, chief.display_name, "Έγκριση και δημοσίευση.")

        items3 = rfq3.items

        # Bid από Office World (χαμηλότερη τιμή)
        bid3a = make_bid(
            rfq3, suppliers[3],  # office_world
            lines_data=[
                (items3[0], 285.00, 5, 24),
                (items3[1], 320.00, 0, 24),
                (items3[2], 145.00, 0, 24),
                (items3[3], 195.00, 5, 24),
                (items3[4], 850.00, 0, 24),
            ],
            shipping=Decimal("80.00"),
            overall_disc_pct=Decimal("2"),
            notes="Παράδοση εντός 20 εργάσιμων ημερών. Συμπεριλαμβάνεται η τοποθέτηση.",
            days_ago=2,
        )
        log(rfq3, suppliers[3].display_name, "Υποβολή προσφοράς.")

        # Bid από Hellas Constructions (ακριβότερη)
        bid3b = make_bid(
            rfq3, suppliers[1],  # hellas_constructions
            lines_data=[
                (items3[0], 310.00, 0, 24),
                (items3[1], 355.00, 5, 24),
                (items3[2], 160.00, 0, 24),
                (items3[3], 210.00, 0, 24),
                (items3[4], 920.00, 0, 24),
            ],
            shipping=Decimal("120.00"),
            notes="Γνωστή εταιρεία επίπλων γραφείου. Εγγύηση 3 ετών.",
            days_ago=3,
        )
        log(rfq3, suppliers[1].display_name, "Υποβολή προσφοράς.")

        # ─────────────────────────────────────────────────────────────────────
        # ── 8. RFQ #4 – PENDING_FINAL_APPROVAL ───────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #4 – PENDING_FINAL_APPROVAL …")
        rfq4 = make_rfq(
            title="Αναβάθμιση Δικτυακής Υποδομής (Switches & Routers)",
            description=(
                "Προμήθεια και εγκατάσταση νέου δικτυακού εξοπλισμού "
                "(managed switches 24-port, firewall, WiFi access points) "
                "για τα κεντρικά γραφεία. Να συνοδεύεται με εγγύηση 3 ετών."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[4], status=RFQStatus.PENDING_FINAL_APPROVAL,
            items_data=[
                ("Managed Switch 24-Port Gigabit (Layer 2)", "τεμ.", 4),
                ("Firewall UTM Appliance (50 χρήστες)", "τεμ.", 1),
                ("WiFi Access Point WiFi 6 (dual-band)", "τεμ.", 6),
                ("Patch Panel 24-port Cat6", "τεμ.", 2),
                ("Rack Cabinet 12U Wall-Mount", "τεμ.", 1),
                ("Καλωδίωση Cat6 (100m ρολό)", "ρολό", 5),
            ],
            allowed_sup_usernames=["techniki_oe", "proio_supply"],
            submit_days_from_now=0, delivery_days_from_now=30,
            created_days_ago=12,
            approved_by=chief.display_name, approved_days_ago=10,
        )
        log(rfq4, emp1.display_name, "Δημιουργία νέας ζήτησης.")
        log(rfq4, chief.display_name, "Έγκριση.")
        items4 = rfq4.items

        bid4 = make_bid(
            rfq4, suppliers[0],  # techniki_oe
            lines_data=[
                (items4[0], 420.00, 5, 24),
                (items4[1], 1850.00, 0, 24),
                (items4[2], 280.00, 3, 24),
                (items4[3], 95.00, 0, 24),
                (items4[4], 340.00, 0, 24),
                (items4[5], 85.00, 0, 24),
            ],
            shipping=Decimal("150.00"),
            overall_disc_pct=Decimal("3"),
            notes="Συμπεριλαμβάνεται εγκατάσταση & ρύθμιση. Εγγύηση 3 ετών.",
            days_ago=5,
        )

        # Η Μαρία (emp1, limit €2.000) έκανε award αλλά το ποσό υπερβαίνει το όριο
        for item in rfq4.items:
            bl = next((l for l in bid4.lines
                       if not l.is_combo and l.request_item_id == item.id), None)
            if bl:
                db.session.add(ItemAward(
                    request_id=rfq4.id, request_item_id=item.id,
                    bid_id=bid4.id, bid_line_id=bl.id,
                    supplier_name=bid4.supplier_name,
                    qty=bl.qty, unit_price=bl.unit_price,
                    line_total=bl.line_total,
                ))
        # shipping award
        ship_bl = next((l for l in bid4.lines if l.is_combo), None)
        if ship_bl:
            db.session.add(ItemAward(
                request_id=rfq4.id, request_item_id=None,
                bid_id=bid4.id, bid_line_id=ship_bl.id,
                supplier_name=bid4.supplier_name,
                qty=ship_bl.qty, unit_price=ship_bl.unit_price,
                line_total=ship_bl.line_total,
            ))
        db.session.flush()
        log(rfq4, emp1.display_name,
            "Αναμονή τελικής έγκρισης από Διευθυντή (Σύνολο > όριο €2.000).")
        notif(chief,
              f"Η ζήτηση #{rfq4.id} υπερβαίνει το όριο και απαιτεί τελική έγκριση.",
              f"/company/requests/{rfq4.id}")

        # ─────────────────────────────────────────────────────────────────────
        # ── 9. RFQ #5 – CLOSED (ανατέθηκε) ──────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #5 – CLOSED (ανατέθηκε) …")
        rfq5 = make_rfq(
            title="Υπηρεσίες Καθαριότητας Κεντρικών Γραφείων – Α' Εξάμηνο 2026",
            description=(
                "Σύναψη σύμβασης παροχής υπηρεσιών καθαριότητας για τα "
                "κεντρικά γραφεία (500τ.μ.), 5 ημέρες/εβδομάδα, Α' Εξάμηνο 2026."
            ),
            created_by_name=emp2.display_name,
            cc=ccs[3], status=RFQStatus.CLOSED,
            items_data=[
                ("Ημερήσιος καθαρισμός γραφείων (Μ/Τ/Τ/Π/Π)", "μήνας", 6),
                ("Βαθύς καθαρισμός τζαμιών εξωτερικά (ανά τρίμηνο)", "φορά", 2),
                ("Αναλώσιμα καθαριότητας (χαρτί, υγρά)", "μήνας", 6),
            ],
            allowed_sup_usernames=["green_clean", "proio_supply"],
            submit_days_from_now=0, delivery_days_from_now=180,
            created_days_ago=30,
            approved_by=chief.display_name, approved_days_ago=28,
        )
        items5 = rfq5.items
        log(rfq5, emp2.display_name, "Δημιουργία.")
        log(rfq5, chief.display_name, "Έγκριση.")

        bid5a = make_bid(
            rfq5, suppliers[4],  # green_clean (χαμηλότερη)
            lines_data=[
                (items5[0], 380.00, 5, 24),
                (items5[1], 250.00, 0, 24),
                (items5[2], 95.00, 0, 24),
            ],
            shipping=Decimal("0"),
            notes="Έμπειρη εταιρεία. 5ετής εμπειρία σε εταιρικά γραφεία.",
            days_ago=20,
        )
        bid5b = make_bid(
            rfq5, suppliers[2],  # proio_supply
            lines_data=[
                (items5[0], 420.00, 0, 24),
                (items5[1], 300.00, 0, 24),
                (items5[2], 110.00, 5, 24),
            ],
            days_ago=19,
        )

        award_all(rfq5, bid5a)
        log(rfq5, emp2.display_name, "Ανάθεση σε Green Clean – καλύτερη τιμή.")
        notif(suppliers[4],
              f"Συγχαρητήρια! Σας ανατέθηκε η παραγγελία #{rfq5.id}.",
              f"/supplier/requests/{rfq5.id}/bid")

        # ─────────────────────────────────────────────────────────────────────
        # ── 10. RFQ #6 – RECEIVED (παραλήφθηκε) ─────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #6 – RECEIVED …")
        rfq6 = make_rfq(
            title="Αγορά Φορητών Υπολογιστών για Πωλητές",
            description=(
                "Προμήθεια 10 φορητών υπολογιστών (14'' FHD, i5, 16GB RAM, "
                "512GB SSD) για την ομάδα πωλήσεων. Να συμπεριλαμβάνεται "
                "τσάντα μεταφοράς & 3ετής εγγύηση."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[4], status=RFQStatus.RECEIVED,
            items_data=[
                ("Laptop 14'' i5-1235U 16GB/512GB SSD Win11 Pro", "τεμ.", 10),
                ("Τσάντα Laptop 14'' Business", "τεμ.", 10),
                ("Mouse Ασύρματο Ergonomic", "τεμ.", 10),
            ],
            allowed_sup_usernames=["techniki_oe", "office_world"],
            submit_days_from_now=0, delivery_days_from_now=0,
            created_days_ago=45,
            approved_by=chief.display_name, approved_days_ago=43,
        )
        items6 = rfq6.items
        log(rfq6, emp1.display_name, "Δημιουργία.")
        log(rfq6, chief.display_name, "Έγκριση.")

        bid6 = make_bid(
            rfq6, suppliers[0],  # techniki_oe
            lines_data=[
                (items6[0], 890.00, 5, 24),
                (items6[1], 42.00,  0, 24),
                (items6[2], 28.00,  0, 24),
            ],
            shipping=Decimal("0"),
            overall_disc_pct=Decimal("2"),
            notes="Dell Latitude 5440. Παράδοση εντός 10 εργάσιμων. Πιστοποιημένος μεταπωλητής.",
            days_ago=38,
            proposed_delivery_days=10,
        )

        award_all(rfq6, bid6)
        rfq6.status = RFQStatus.RECEIVED
        receive_all(rfq6)
        log(rfq6, emp1.display_name, "Οριστική ολοκλήρωση παραλαβής.")

        # ─────────────────────────────────────────────────────────────────────
        # ── 11. RFQ #7 – DENIED ───────────────────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #7 – DENIED …")
        rfq7 = make_rfq(
            title="Αγορά Εκτυπωτή A3 Έγχρωμου Laser",
            description="Αγορά 1 εκτυπωτή A3 laser έγχρωμου για το τμήμα σχεδιασμού.",
            created_by_name=emp2.display_name,
            cc=ccs[0], status=RFQStatus.DENIED,
            items_data=[
                ("Εκτυπωτής A3 Laser Έγχρωμος (WiFi, Duplex)", "τεμ.", 1),
                ("Toner Set (CMYK) για A3 εκτυπωτή", "σετ", 2),
            ],
            allowed_sup_usernames=["office_world"],
            submit_days_from_now=0, delivery_days_from_now=0,
            created_days_ago=20,
            denial_reason=(
                "Ο προϋπολογισμός του έργου CC-001 έχει εξαντληθεί για το "
                "τρέχον τρίμηνο. Παρακαλώ επανυποβάλετε στο Β' τρίμηνο."
            ),
        )
        log(rfq7, emp2.display_name, "Δημιουργία.")
        log(rfq7, chief.display_name,
            "Απόρριψη: Προϋπολογισμός έργου CC-001 εξαντλήθηκε.")
        notif(emp2, f"Η ζήτηση #{rfq7.id} απορρίφθηκε.",
              f"/company/requests/{rfq7.id}")

        # ─────────────────────────────────────────────────────────────────────
        # ── 12. RFQ #8 – CANCELLED ────────────────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #8 – CANCELLED …")
        rfq8 = make_rfq(
            title="Μίσθωση Κλαρκ για Αποθήκη Πειραιά (Μηνιαία)",
            description=(
                "Μηνιαία μίσθωση ηλεκτρικού κλαρκ (ανυψωτική ικανότητα 2.5τ.) "
                "για τις ανάγκες της αποθήκης."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[1], status=RFQStatus.CANCELLED,
            items_data=[
                ("Ηλεκτρικός Κλαρκ 2.5τ. (μηνιαία μίσθωση)", "μήνας", 3),
            ],
            allowed_sup_usernames=["techniki_oe"],
            submit_days_from_now=0, delivery_days_from_now=0,
            created_days_ago=15,
        )
        log(rfq8, emp1.display_name, "Δημιουργία.")
        log(rfq8, emp1.display_name,
            "Ακύρωση ζήτησης – η ανάγκη καλύφθηκε εσωτερικά.")

        # ─────────────────────────────────────────────────────────────────────
        # ── 13. RFQ #9 – OPEN με 3 ανταγωνιστικές προσφορές ─────────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #9 – OPEN (3 ανταγωνιστικές προσφορές) …")
        rfq9 = make_rfq(
            title="Προμήθεια Υλικών Συντήρησης Αποθήκης",
            description=(
                "Αγορά υλικών για τις εργασίες συντήρησης της αποθήκης Πειραιά: "
                "βαφές, εργαλεία, αναλώσιμα. Απαραίτητη η έκδοση δελτίου αποστολής."
            ),
            created_by_name=emp2.display_name,
            cc=ccs[1], status=RFQStatus.OPEN,
            items_data=[
                ("Βαφή Τοίχου Λευκή (20L κουβάς)", "κουβάς", 10),
                ("Ρολό Βαφής (σετ 5τμχ)", "σετ", 6),
                ("Σιλικόνη Αρμοστοκτόνος 280ml", "τεμ.", 20),
                ("Αλουμινόχαρτο Αλουμινίου Μονωτικό (10m²)", "πακέτο", 8),
                ("Γάντια Εργασίας Latex (κουτί 100τμχ)", "κουτί", 5),
            ],
            allowed_sup_usernames=["techniki_oe", "proio_supply", "hellas_constructions"],
            submit_days_from_now=7, delivery_days_from_now=21,
            created_days_ago=8,
            approved_by=chief.display_name, approved_days_ago=7,
        )
        items9 = rfq9.items
        log(rfq9, emp2.display_name, "Δημιουργία.")
        log(rfq9, chief.display_name, "Έγκριση.")

        bid9a = make_bid(
            rfq9, suppliers[0],  # techniki_oe
            lines_data=[
                (items9[0], 32.50, 0, 24),
                (items9[1], 18.00, 0, 24),
                (items9[2], 5.80,  0, 24),
                (items9[3], 45.00, 5, 24),
                (items9[4], 12.00, 0, 24),
            ],
            shipping=Decimal("30.00"), days_ago=4,
        )
        bid9b = make_bid(
            rfq9, suppliers[2],  # proio_supply
            lines_data=[
                (items9[0], 30.00, 0, 24),
                (items9[1], 19.50, 5, 24),
                (items9[2], 5.50,  0, 24),
                (items9[3], 42.00, 0, 24),
                (items9[4], 11.50, 0, 24),
            ],
            shipping=Decimal("25.00"),
            notes="Άμεση διαθεσιμότητα. Παράδοση 2–3 εργάσιμες.",
            days_ago=3,
        )
        bid9c = make_bid(
            rfq9, suppliers[1],  # hellas_constructions
            lines_data=[
                (items9[0], 34.00, 0, 24),
                (items9[1], 17.50, 0, 24),
                (items9[2], 6.20,  0, 24),
                (items9[3], 48.00, 3, 24),
                (items9[4], 13.00, 5, 24),
            ],
            shipping=Decimal("0"),
            overall_disc_pct=Decimal("5"),
            notes="Δωρεάν μεταφορικά για αγορές άνω 200€.",
            days_ago=2,
        )
        log(rfq9, suppliers[0].display_name, "Υποβολή προσφοράς.")
        log(rfq9, suppliers[2].display_name, "Υποβολή προσφοράς.")
        log(rfq9, suppliers[1].display_name, "Υποβολή προσφοράς.")

        # ─────────────────────────────────────────────────────────────────────
        # ── 14. RFQ #10 – CLOSED (split award σε 2 προμηθευτές) ──────────────
        # ─────────────────────────────────────────────────────────────────────
        print("📋 RFQ #10 – CLOSED (split award) …")
        rfq10 = make_rfq(
            title="Εξοπλισμός Κουζίνας & Χώρου Ανάπαυσης",
            description=(
                "Αγορά εξοπλισμού για την ανακαινισμένη κουζίνα / breakroom "
                "των κεντρικών γραφείων."
            ),
            created_by_name=emp1.display_name,
            cc=ccs[0], status=RFQStatus.CLOSED,
            items_data=[
                ("Καφετιέρα Espresso επαγγελματική (group 2)", "τεμ.", 1),
                ("Ψυγείο Μίνι-Μπαρ 60L", "τεμ.", 2),
                ("Φούρνος Μικροκυμάτων 25L", "τεμ.", 2),
                ("Πάγκος Εργασίας Inox 120×60cm", "τεμ.", 1),
                ("Σετ Φλιτζάνια Espresso (12τμχ)", "σετ", 3),
            ],
            allowed_sup_usernames=["office_world", "proio_supply"],
            submit_days_from_now=0, delivery_days_from_now=0,
            created_days_ago=25,
            approved_by=chief.display_name, approved_days_ago=23,
        )
        items10 = rfq10.items
        log(rfq10, emp1.display_name, "Δημιουργία.")
        log(rfq10, chief.display_name, "Έγκριση.")

        bid10a = make_bid(
            rfq10, suppliers[3],  # office_world
            lines_data=[
                (items10[0], 1200.00, 0, 24),
                (items10[1], 185.00,  5, 24),
                (items10[2], 145.00,  0, 24),
                (items10[3], 320.00,  0, 24),
                (items10[4], 38.00,   0, 24),
            ],
            days_ago=15,
        )
        bid10b = make_bid(
            rfq10, suppliers[2],  # proio_supply
            lines_data=[
                (items10[0], 1050.00, 5, 24),
                (items10[1], 195.00,  0, 24),
                (items10[2], 138.00,  3, 24),
                (items10[3], 295.00,  0, 24),
                (items10[4], 42.00,   0, 24),
            ],
            days_ago=14,
        )

        # Split award: items 0,3,4 → proio_supply  |  items 1,2 → office_world
        for idx, bid_obj in [(0, bid10b), (3, bid10b), (4, bid10b),
                             (1, bid10a), (2, bid10a)]:
            item = items10[idx]
            bl = next((l for l in bid_obj.lines
                       if not l.is_combo and l.request_item_id == item.id), None)
            if bl:
                db.session.add(ItemAward(
                    request_id=rfq10.id, request_item_id=item.id,
                    bid_id=bid_obj.id, bid_line_id=bl.id,
                    supplier_name=bid_obj.supplier_name,
                    qty=bl.qty, unit_price=bl.unit_price,
                    line_total=bl.line_total,
                ))
        db.session.flush()
        log(rfq10, emp1.display_name,
            "Split award: Καφετιέρα/Πάγκος/Φλιτζάνια → Πρώιο, Ψυγεία/Φούρνοι → Office World.")
        notif(suppliers[3], f"Σας ανατέθηκε μέρος της παραγγελίας #{rfq10.id}.",
              f"/supplier/requests/{rfq10.id}/bid")
        notif(suppliers[2], f"Σας ανατέθηκε μέρος της παραγγελίας #{rfq10.id}.",
              f"/supplier/requests/{rfq10.id}/bid")

        # ─────────────────────────────────────────────────────────────────────
        # ── 15. Commit ────────────────────────────────────────────────────────
        # ─────────────────────────────────────────────────────────────────────
        db.session.commit()
        print()
        print("✅ Τα δεδομένα δημιουργήθηκαν επιτυχώς!")
        print()
        print("┌─────────────────────────────────┬──────────────┬────────────┐")
        print("│ Username                        │ Password     │ Ρόλος      │")
        print("├─────────────────────────────────┼──────────────┼────────────┤")
        print("│ nikos.papadopoulos              │ Chief123!    │ chief      │")
        print("│ maria.georgiou                  │ Company123!  │ company    │")
        print("│ kostas.antoniou                 │ Company123!  │ company    │")
        print("│ techniki_oe                     │ Supplier1!   │ supplier   │")
        print("│ hellas_constructions            │ Supplier2!   │ supplier   │")
        print("│ proio_supply                    │ Supplier3!   │ supplier   │")
        print("│ office_world                    │ Supplier4!   │ supplier   │")
        print("│ green_clean                     │ Supplier5!   │ supplier   │")
        print("└─────────────────────────────────┴──────────────┴────────────┘")
        print()
        print("RFQs που δημιουργήθηκαν:")
        for rfq in RequestRFQ.query.order_by(RequestRFQ.id).all():
            print(f"  #{rfq.id:2d}  [{rfq.status:<25s}]  {rfq.title[:55]}")


if __name__ == "__main__":
    seed()
