from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from decimal import Decimal

db = SQLAlchemy()

class User(db.Model):
    """
    Μοντέλο Χρήστη: Διαχειρίζεται τα στοιχεία σύνδεσης και τους ρόλους (chief, company, supplier).
    """
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)
    first_name = db.Column(db.String(120), nullable=True)
    last_name  = db.Column(db.String(120), nullable=True)

    # Σχέση με τις προσφορές που έχει υποβάλει ο χρήστης (αν είναι προμηθευτής)
    bids = db.relationship("Bid", backref="supplier", lazy=True)

    def set_password(self, password: str):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class SupplierProfile(db.Model):
    """
    Προφίλ Προμηθευτή: Επιπλέον επαγγελματικά στοιχεία για τους χρήστες με ρόλο 'supplier'.
    """
    __tablename__ = "supplier_profiles"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    company_name = db.Column(db.String(200))
    tax_id = db.Column(db.String(32))
    contact_name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.String(250))
    city = db.Column(db.String(120))
    postal_code = db.Column(db.String(20))
    iban = db.Column(db.String(34))
    notes = db.Column(db.Text)
    user = db.relationship("User", backref=db.backref("profile", uselist=False, cascade="all,delete"))

class CostCenter(db.Model):
    """
    Κέντρο Κόστους / Έργο: Διαχείριση των διαθέσιμων έργων της εταιρείας.
    """
    __tablename__ = "cost_centers"
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    address = db.Column(db.String(250), nullable=True)             # Διεύθυνση Έργου
    project_manager = db.Column(db.String(120), nullable=True)     # Υπεύθυνος Έργου
    receiving_manager = db.Column(db.String(120), nullable=True)   # Υπεύθυνος Παραλαβής
    phone = db.Column(db.String(50), nullable=True)                # Τηλέφωνο

class RequestRFQ(db.Model):
    """
    Ζήτηση Προσφοράς (RFQ): Το κεντρικό έγγραφο που δημιουργεί η εταιρεία.
    """
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    documents = db.Column(db.String(255), nullable=True)
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    delivery_location = db.Column(db.String(255), nullable=True)
    receiving_manager = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    
    submit_deadline = db.Column(db.DateTime, nullable=False)
    delivery_deadline = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='open') # pending, open, closed, denied
    
    approved_by = db.Column(db.String(100), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    denial_reason = db.Column(db.Text, nullable=True)
    
    winning_bid_id = db.Column(db.Integer, db.ForeignKey('bids.id'), nullable=True)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)

    # Σχέση με το Έργο
    cost_center = db.relationship('CostCenter', backref='rfqs')

    items = db.relationship('RequestItem', backref='rfq', lazy=True, cascade="all, delete-orphan")
    bids = db.relationship('Bid', backref='rfq', lazy=True, foreign_keys="[Bid.request_id]", cascade="all, delete-orphan")
    allowed_suppliers = db.relationship('AllowedSupplier', backref='rfq', lazy=True, cascade="all, delete-orphan")

class RequestItem(db.Model):
    """
    Είδος Ζήτησης: Τα συγκεκριμένα υλικά ή υπηρεσίες που ζητούνται σε ένα RFQ.
    """
    __tablename__ = "request_items"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Numeric(12, 2), nullable=False)

class Bid(db.Model):
   
    __tablename__ = "bids"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False) # Σύνδεση με το ID του χρήστη
    supplier_name = db.Column(db.String(120), nullable=False) # Αντιγραφή ονόματος για ιστορικότητα
    price = db.Column(db.Numeric(12, 2), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='draft') 
    status = db.Column(db.String(20), default='draft') 
    overall_discount_type = db.Column(db.String(10), default='pct') 
    proposed_delivery_date = db.Column(db.DateTime, nullable=True) 
   
    is_draft = db.Column(db.Boolean, default=False) 
    
    subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    discount_total = db.Column(db.Numeric(12, 2), nullable=True)
    overall_discount_pct = db.Column(db.Numeric(5, 2), nullable=True)
    shipping_cost = db.Column(db.Numeric(12, 2), nullable=True)
    vat_pct = db.Column(db.Numeric(5, 2), nullable=True)
    vat_amount = db.Column(db.Numeric(12, 2), nullable=True)
    
    lines = db.relationship("BidLine", backref="bid", cascade="all, delete-orphan", lazy=True)

class BidLine(db.Model):

    __tablename__ = "bid_lines"
    id = db.Column(db.Integer, primary_key=True)
    bid_id = db.Column(db.Integer, db.ForeignKey("bids.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey("request_items.id"), nullable=True)
    is_combo = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(255), nullable=False)
    unit = db.Column(db.String(50), nullable=True)
    qty = db.Column(db.Numeric(12, 2), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_pct = db.Column(db.Numeric(5, 2), nullable=True)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=True)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)
    merged_items = db.Column(db.Text, nullable=True)
    discount_type = db.Column(db.String(10), default='pct')
    vat_pct = db.Column(db.Numeric(5, 2), default=24)
    
    # Προσθήκη χρόνου παράδοσης ανά είδος
    delivery_days = db.Column(db.Integer, nullable=True)

class ItemAward(db.Model):
    """
    Ανάθεση Είδους: Καταγραφή του νικητή προμηθευτή για κάθε είδος.
    """
    __tablename__ = "item_awards"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey('request_items.id'), nullable=True)
    bid_id = db.Column(db.Integer, db.ForeignKey("bids.id"), nullable=False)
    bid_line_id = db.Column(db.Integer, db.ForeignKey("bid_lines.id"), nullable=True)
    supplier_name = db.Column(db.String(120), nullable=False)
    qty = db.Column(db.Numeric(12, 2), nullable=True)
    unit_price = db.Column(db.Numeric(12, 2), nullable=True)
    line_total = db.Column(db.Numeric(12, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bid = db.relationship("Bid", backref="item_awards", lazy=True)

class ItemReceipt(db.Model):
    """
    Παραλαβή Είδους: Καταγραφή της φυσικής παραλαβής των υλικών.
    """
    __tablename__ = "item_receipts"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    request_item_id = db.Column(db.Integer, db.ForeignKey("request_items.id"), nullable=False)
    awarded_supplier = db.Column(db.String(120), nullable=True)
    received_qty = db.Column(db.Numeric(12, 2), nullable=True)
    received_by = db.Column(db.String(120), nullable=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow)

class AllowedSupplier(db.Model):
    """
    Επιτρεπόμενος Προμηθευτής: Πίνακας προσκλήσεων για συγκεκριμένες ζητήσεις.
    """
    __tablename__ = "allowed_suppliers"
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("requests.id"), nullable=False)
    supplier_username = db.Column(db.String(100), nullable=False)