from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from reportlab.lib import colors

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///budget_guardian.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- Database Models ---
class BudgetBucket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), unique=True)
    allocated = db.Column(db.Float)
    spent = db.Column(db.Float, default=0.0)

class ExpenseLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(100))
    amount = db.Column(db.Float)
    category = db.Column(db.String(50))
    date_added = db.Column(db.DateTime, default=datetime.now)

# --- AI Logic ---
def get_ai_alerts(buckets):
    day = datetime.now().day
    alerts = []
    for b in buckets:
        if b.allocated > 0 and b.spent > 0:
            projected = (b.spent / day) * 30
            if projected > b.allocated:
                over = projected - b.allocated
                alerts.append(f"{b.category}: Projected to overspend by {over:,.0f} PKR.")
    return alerts

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        item = request.form.get('item_name')
        amt = float(request.form.get('amount', 0))
        cat = request.form.get('category')
        
        bucket = BudgetBucket.query.filter_by(category=cat).first()
        if bucket:
            bucket.spent += amt
            db.session.add(ExpenseLog(item_name=item, amount=amt, category=cat))
            db.session.commit()
        return redirect(url_for('index'))

    buckets = BudgetBucket.query.all()
    history = ExpenseLog.query.order_by(ExpenseLog.date_added.desc()).all()
    total_spent = sum(b.spent for b in buckets)
    total_income = sum(b.allocated for b in buckets)
    ai_warnings = get_ai_alerts(buckets)

    return render_template('index.html', buckets=buckets, history=history,
                           total_spent=total_spent, total_income=total_income,
                           ai_warnings=ai_warnings)

@app.route('/delete_entry/<int:id>')
def delete_entry(id):
    entry = ExpenseLog.query.get(id)
    if entry:
        bucket = BudgetBucket.query.filter_by(category=entry.category).first()
        if bucket:
            bucket.spent -= entry.amount
        db.session.delete(entry)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/update_settings', methods=['POST'])
def update_settings():
    for key, value in request.form.items():
        if key.startswith('alloc_') and value:
            bucket_id = key.split('_')[1]
            bucket = BudgetBucket.query.get(bucket_id)
            if bucket:
                bucket.allocated = float(value)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/master_reset')
def master_reset():
    db.drop_all()
    db.create_all()
    # Default initial buckets
    db.session.add_all([
        BudgetBucket(category="Grocery", allocated=30000),
        BudgetBucket(category="Petrol", allocated=10000),
        BudgetBucket(category="Rent", allocated=50000),
        BudgetBucket(category="Misc", allocated=5000)
    ])
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/export_pdf')
def export_pdf():
    history = ExpenseLog.query.order_by(ExpenseLog.date_added.desc()).all()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    data = [["Date", "Item", "Category", "Amount"]]
    for log in history:
        data.append([log.date_added.strftime('%d-%b'), log.item_name, log.category, f"{log.amount:,.0f}"])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d16ba5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="SunsLedger_Report.pdf")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not BudgetBucket.query.first():
            db.session.add_all([
                BudgetBucket(category="Grocery", allocated=30000),
                BudgetBucket(category="Petrol", allocated=10000)
            ])
            db.session.commit()
    app.run(debug=True, port=8080)
