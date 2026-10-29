from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
import sqlite3

app = FastAPI(title="Nexovant / Lumetra Technologies Platform")

USD_TO_PKR = 278.50

def get_db():
    conn = sqlite3.connect("platform.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Investor Waitlist & Cap-Table Preview
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS investor_waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            intended_pkr REAL NOT NULL,
            is_fbr_filer INTEGER DEFAULT 1
        )
    """)

    # 2. Export Revenue Ledger (SBP Code 9186 Audit Trail)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            country TEXT NOT NULL,
            service_type TEXT NOT NULL,
            amount_usd REAL NOT NULL,
            sbp_code TEXT DEFAULT '9186',
            prc_reference TEXT NOT NULL
        )
    """)

    # 3. B2B Software & ERP Client Inquiries
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            solution_tier TEXT NOT NULL,
            estimated_usd REAL NOT NULL
        )
    """)

    # Seed sample export invoices if table is empty so the dashboard has initial data
    count = cursor.execute("SELECT COUNT(*) FROM export_invoices").fetchone()[0]
    if count == 0:
        cursor.executemany(
            "INSERT INTO export_invoices (client_name, country, service_type, amount_usd, prc_reference) VALUES (?, ?, ?, ?, ?)",
            [
                ("Apex Retail Group", "United Kingdom", "Cloud ERP Enterprise License", 3500.0, "PRC-SBP-9186-001"),
                ("Nordic Logistics AB", "Sweden", "Flutter + FastAPI Custom Module", 4500.0, "PRC-SBP-9186-002"),
            ]
        )

    conn.commit()
    conn.close()

init_db()

class InvestorSignup(BaseModel):
    full_name: str
    email: str
    whatsapp: str
    intended_pkr: float
    is_fbr_filer: bool

class ExportInvoiceIn(BaseModel):
    client_name: str
    country: str
    service_type: str
    amount_usd: float
    prc_reference: str

class ClientLeadIn(BaseModel):
    company_name: str
    contact_email: str
    solution_tier: str
    estimated_usd: float

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Silences the 404 favicon log in your terminal
    return Response(status_code=204)

@app.post("/api/waitlist")
def join_waitlist(investor: InvestorSignup):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO investor_waitlist (full_name, email, whatsapp, intended_pkr, is_fbr_filer) VALUES (?, ?, ?, ?, ?)",
        (investor.full_name, investor.email, investor.whatsapp, investor.intended_pkr, int(investor.is_fbr_filer))
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"{investor.full_name} added to the Shareholder Waitlist."}

@app.post("/api/invoices")
def add_export_invoice(inv: ExportInvoiceIn):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO export_invoices (client_name, country, service_type, amount_usd, prc_reference) VALUES (?, ?, ?, ?, ?)",
        (inv.client_name, inv.country, inv.service_type, inv.amount_usd, inv.prc_reference)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Export invoice logged under SBP Code 9186."}

@app.post("/api/leads")
def create_client_lead(lead: ClientLeadIn):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO client_leads (company_name, contact_email, solution_tier, estimated_usd) VALUES (?, ?, ?, ?)",
        (lead.company_name, lead.contact_email, lead.solution_tier, lead.estimated_usd)
    )
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Quote request received for {lead.company_name}."}

@app.get("/api/dashboard")
def get_dashboard_summary():
    conn = get_db()
    invoices = [dict(row) for row in conn.execute("SELECT * FROM export_invoices ORDER BY id DESC").fetchall()]
    investors = [dict(row) for row in conn.execute("SELECT * FROM investor_waitlist ORDER BY id DESC").fetchall()]
    leads = [dict(row) for row in conn.execute("SELECT * FROM client_leads ORDER BY id DESC").fetchall()]
    conn.close()

    total_usd = sum(i["amount_usd"] for i in invoices)
    gross_pkr = total_usd * USD_TO_PKR
    pseb_tax_pkr = gross_pkr * 0.0025          # 0.25% FBR IT Export Final Tax
    operating_cost_pkr = gross_pkr * 0.30      # 30% Engineering & Cloud Ops
    net_profit_pkr = gross_pkr - pseb_tax_pkr - operating_cost_pkr
    dividend_pool_pkr = net_profit_pkr * 0.60  # 60% Distributed to Shareholders

    total_committed_pkr = sum(inv["intended_pkr"] for inv in investors) or 1.0

    # Calculate each investor's projected quarterly dividend & FBR Withholding Tax
    investor_payouts = []
    for inv in investors:
        share_ratio = inv["intended_pkr"] / total_committed_pkr
        gross_dividend = dividend_pool_pkr * share_ratio
        wht_rate = 0.15 if inv["is_fbr_filer"] else 0.30
        wht_tax = gross_dividend * wht_rate
        net_dividend = gross_dividend - wht_tax
        investor_payouts.append({
            **inv,
            "equity_ pool_share_pct": round(share_ratio * 100, 2),
            "gross_dividend_pkr": round(gross_dividend),
            "wht_tax_pkr": round(wht_tax),
            "net_dividend_pkr": round(net_dividend)
        })

    return {
        "metrics": {
            "total_export_usd": round(total_usd, 2),
            "gross_export_pkr": round(gross_pkr),
            "pseb_tax_pkr": round(pseb_tax_pkr),
            "net_profit_pkr": round(net_profit_pkr),
            "dividend_pool_pkr": round(dividend_pool_pkr),
            "total_committed_capital_pkr": round( sum(inv["intended_pkr"] for inv in investors) )
        },
        "invoices": invoices,
        "investors": investor_payouts,
        "leads": leads
    }

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def serve_home():
    return FileResponse("static/index.html")