import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, date
import plotly.express as px
import io
import os

DB_FILE = "expenses_upgraded.db"

# -------------------------
# Database helpers
# -------------------------
def get_conn():
    os.makedirs(".", exist_ok=True)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()
    # members / users
    c.execute("""
    CREATE TABLE IF NOT EXISTS members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT
    );
    """)
    # transactions
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        ttype TEXT NOT NULL,   -- 'income' or 'expense'
        category TEXT,
        amount REAL NOT NULL,
        date TEXT NOT NULL,    -- ISO date
        notes TEXT,
        FOREIGN KEY(member_id) REFERENCES members(id)
    );
    """)
    # budgets per member monthly
    c.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        member_id INTEGER,
        monthly_budget REAL,
        currency TEXT DEFAULT 'INR',
        FOREIGN KEY(member_id) REFERENCES members(id)
    );
    """)
    conn.commit()
    conn.close()

def add_member(username, display_name=None):
    conn = get_conn(); c = conn.cursor()
    try:
        c.execute("INSERT INTO members (username, display_name) VALUES (?,?)", (username, display_name or username))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    c.execute("SELECT id, username, display_name FROM members WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    return row

def get_members():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id, username, display_name FROM members ORDER BY id")
    rows = c.fetchall(); conn.close()
    return rows

def add_transaction(member_id, ttype, category, amount, date_iso, notes=""):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO transactions (member_id, ttype, category, amount, date, notes) VALUES (?,?,?,?,?,?)",
              (member_id, ttype, category, amount, date_iso, notes))
    conn.commit(); conn.close()

def delete_transaction(tx_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit(); conn.close()

def get_transactions_df(member_id=None, start=None, end=None, category=None, ttype=None):
    conn = get_conn(); c = conn.cursor()
    q = "SELECT t.id, t.member_id, m.username, m.display_name, t.ttype, t.category, t.amount, t.date, t.notes FROM transactions t LEFT JOIN members m ON t.member_id = m.id WHERE 1=1"
    params = []
    if member_id:
        q += " AND member_id=?"; params.append(member_id)
    if category:
        q += " AND category = ?"; params.append(category)
    if ttype:
        q += " AND ttype = ?"; params.append(ttype)
    if start:
        q += " AND date(t.date) >= date(?)"; params.append(start)
    if end:
        q += " AND date(t.date) <= date(?)"; params.append(end)
    q += " ORDER BY date(t.date) DESC, t.id DESC"
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame(columns=["id","member_id","username","display_name","ttype","category","amount","date","notes"])
    df = pd.DataFrame([dict(r) for r in rows])
    # normalize types and date
    df["amount"] = df["amount"].astype(float)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def set_budget(member_id, monthly_budget):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id FROM budgets WHERE member_id=?", (member_id,))
    if c.fetchone():
        c.execute("UPDATE budgets SET monthly_budget=? WHERE member_id=?", (monthly_budget, member_id))
    else:
        c.execute("INSERT INTO budgets (member_id, monthly_budget) VALUES (?,?)", (member_id, monthly_budget))
    conn.commit(); conn.close()

def get_budget(member_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT monthly_budget, currency FROM budgets WHERE member_id=?", (member_id,))
    row = c.fetchone(); conn.close()
    return row

# initialize DB
init_db()

# -------------------------
# App UI & Logic
# -------------------------
st.set_page_config(page_title="Expense Tracker — Dark Pink", layout="wide")
# Theme CSS
st.markdown(
    """
    <style>
    body, .stApp { background-color: #000000; color: #ff66b2; }
    .css-1v0mbdj { color: #ff66b2; } /* headings */
    .stButton>button, .stDownloadButton>button { background-color:#ff66b2; color:#000; font-weight:600; border-radius:8px; }
    .stSelectbox, .stTextInput, .stNumberInput, .stDateInput, .stTextArea { color: #ff66b2; }
    .stDataFrame table { color: #ff66b2; }
    </style>
    """, unsafe_allow_html=True
)

st.title("💖 Family Expense Tracker")

# Quick login / member create (any username allowed)
st.sidebar.header("Quick Sign-in (auto-create)")
username = st.sidebar.text_input("Username (unique)")
display_name = st.sidebar.text_input("Display name (optional)")
if st.sidebar.button("Sign in"):
    if not username.strip():
        st.sidebar.error("Enter a username.")
    else:
        row = add_member(username.strip(), display_name.strip() or None)
        st.session_state["member"] = {"id": row["id"], "username": row["username"], "display_name": row["display_name"]}
        st.sidebar.success(f"Signed in as {row['username']}")

if "member" in st.session_state:
    m = st.session_state["member"]
    st.sidebar.markdown(f"**Current:** {m['display_name'] or m['username']} (id: {m['id']})")
    if st.sidebar.button("Sign out"):
        del st.session_state["member"]
        st.rerun()

else:
    st.sidebar.info("Sign in with any username to create/select a member account.")

# Tabs
tabs = st.tabs(["Dashboard", "Add Transaction", "Transactions", "Import/Export", "Settings"])
members = get_members()
member_options = {r["display_name"] or r["username"]: r["id"] for r in members}

# -------------------------
# Dashboard tab
# -------------------------
with tabs[0]:
    st.header("📊 Dashboard")
    # filters
    colf1, colf2, colf3 = st.columns(3)
    with colf1:
        view_member = st.selectbox("View member", options=["Family (All)"] + list(member_options.keys()))
    with colf2:
        start_date = st.date_input("Start date", value=date.today().replace(day=1))
    with colf3:
        end_date = st.date_input("End date", value=date.today())

    sel_member_id = None if view_member.startswith("Family") else member_options.get(view_member)
    df = get_transactions_df(member_id=sel_member_id, start=start_date.isoformat(), end=end_date.isoformat())

    if df.empty:
        st.info("No transactions in the selected range.")
    else:
        # summary metrics
        total_income = df[df["ttype"]=="income"]["amount"].sum()
        total_expense = df[df["ttype"]=="expense"]["amount"].sum()
        net = total_income - total_expense
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Income", f"₹{total_income:,.2f}")
        c2.metric("Total Expense", f"₹{total_expense:,.2f}")
        c3.metric("Net Balance", f"₹{net:,.2f}")

        # monthly net line
        df["ym"] = pd.to_datetime(df["date"]).apply(lambda d: d.strftime("%Y-%m"))
        monthly = df.groupby("ym").apply(lambda x: x[x["ttype"]=="income"]["amount"].sum() - x[x["ttype"]=="expense"]["amount"].sum()).reset_index(name="net")
        fig_month = px.line(monthly, x="ym", y="net", title="Monthly Net (Income - Expense)")
        st.plotly_chart(fig_month, use_container_width=True)

        # top categories
        exp_df = df[df["ttype"]=="expense"]
        if not exp_df.empty:
            cat = exp_df.groupby("category")["amount"].sum().reset_index().sort_values("amount", ascending=False)
            fig_cat = px.bar(cat, x="category", y="amount", title="Top Expense Categories")
            st.plotly_chart(fig_cat, use_container_width=True)

        # member comparison (if family)
        if sel_member_id is None:
            comp = df.groupby("username").apply(lambda x: x[x["ttype"]=="expense"]["amount"].sum()).reset_index(name="expense")
            if not comp.empty:
                fig_comp = px.bar(comp, x="username", y="expense", title="Expense by Member")
                st.plotly_chart(fig_comp, use_container_width=True)

    # budget section
    st.markdown("---")
    st.subheader("Budgets & Alerts")
    if members:
        for r in members:
            b = get_budget(r["id"])
            monthly_budget = b["monthly_budget"] if b else 0
            # compute current month spend
            today = date.today()
            start_m = today.replace(day=1).isoformat()
            spent_df = get_transactions_df(member_id=r["id"], start=start_m, end=today.isoformat())
            spent = spent_df[spent_df["ttype"]=="expense"]["amount"].sum()
            pct = (spent / monthly_budget) if monthly_budget>0 else 0
            colA, colB = st.columns([3,1])
            with colA:
                st.write(f"**{r['display_name'] or r['username']}** — Budget: ₹{monthly_budget:,.0f} — Spent: ₹{spent:,.0f}")
                if monthly_budget>0:
                    st.progress(min(pct,1.0))
                    if pct >= 1:
                        st.error(f"{r['display_name'] or r['username']} exceeded the monthly budget!")
                    elif pct >= 0.8:
                        st.warning(f"{r['display_name'] or r['username']} used {pct*100:.0f}% of budget.")
            with colB:
                # quick set budget button opens small input
                if st.button(f"Set budget for {r['id']}", key=f"bbtn_{r['id']}"):
                    val = st.number_input(f"Monthly budget (₹) for {r['display_name'] or r['username']}", min_value=0.0, key=f"budget_input_{r['id']}")
                    if st.button("Save budget", key=f"save_budget_{r['id']}"):
                        set_budget(r["id"], float(val))
                        st.rerun()

    else:
        st.info("Create members in Settings tab to track budgets.")

# -------------------------
# Add Transaction tab
# -------------------------
with tabs[1]:
    st.header("➕ Add Transaction")
    if "member" not in st.session_state:
        st.warning("Sign in (sidebar) or create a member in Settings to add transactions.")
    else:
        member_id = st.session_state["member"]["id"]
        with st.form("add_tx"):
            ttype = st.selectbox("Type", ["expense", "income"])
            category = st.text_input("Category", value="General")
            amount = st.number_input("Amount", min_value=0.0, format="%.2f")
            tx_date = st.date_input("Date", value=date.today())
            notes = st.text_area("Notes (optional)")
            submitted = st.form_submit_button("Save")
            if submitted:
                add_transaction(member_id, ttype, category, float(amount), tx_date.isoformat(), notes or "")
                st.success("Transaction added.")
                st.rerun()


# -------------------------
# Transactions tab
# -------------------------
with tabs[2]:
    st.header("📋 Transactions")
    # filters
    fcol1, fcol2, fcol3, fcol4 = st.columns(4)
    with fcol1:
        sel_member = st.selectbox("Member filter", options=["All"] + list(member_options.keys()))
    with fcol2:
        sel_cat = st.text_input("Category (exact) or leave empty")
    with fcol3:
        sel_type = st.selectbox("Type", options=["All","income","expense"])
    with fcol4:
        date_from = st.date_input("From", value=(date.today().replace(day=1)))
        date_to = st.date_input("To", value=date.today())

    m_id = None if sel_member=="All" else member_options.get(sel_member)
    cat = sel_cat if sel_cat.strip() else None
    ttype_filter = None if sel_type=="All" else sel_type

    trans_df = get_transactions_df(member_id=m_id, start=date_from.isoformat(), end=date_to.isoformat(), category=cat, ttype=ttype_filter)
    st.dataframe(trans_df[["id","username","display_name","ttype","category","amount","date","notes"]])

    st.markdown("### Delete transaction by ID")
    del_id = st.number_input("Transaction ID to delete", min_value=0, step=1, value=0)
    if st.button("Delete"):
        if del_id>0:
            delete_transaction(int(del_id))
            st.success(f"Deleted {del_id}")
            st.rerun()

        else:
            st.error("Enter a valid id > 0")

# -------------------------
# Import / Export tab
# -------------------------
with tabs[3]:
    st.header("⚙️ Import & Export")
    # Export CSV
    all_df = get_transactions_df()
    if not all_df.empty:
        csv = all_df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download All Transactions (CSV)", csv, "transactions_all.csv", "text/csv")
    else:
        st.info("No transactions to export.")

    # Export DB file
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            db_bytes = f.read()
        st.download_button("📥 Download SQLite DB (backup)", db_bytes, DB_FILE, "application/x-sqlite3")

    st.markdown("---")
    st.subheader("Import transactions from CSV")
    st.markdown("CSV columns must include: username, date(YYYY-MM-DD), member(optional), ttype(income|expense), category, amount, notes(optional).")
    up = st.file_uploader("Upload CSV", type=["csv"])
    if up:
        try:
            df_in = pd.read_csv(up)
            # basic normalization and insert
            inserted = 0
            for _, r in df_in.iterrows():
                uname = str(r.get("username") or r.get("user") or "import_user")
                # ensure member exists
                row = add_member(uname, uname)
                member_id = row["id"]
                date_iso = str(r.get("date"))[:10]
                ttype = str(r.get("ttype") or r.get("type") or "expense")
                category = str(r.get("category") or "Imported")
                amount = float(r.get("amount") or 0)
                notes = str(r.get("notes") or "")
                add_transaction(member_id, ttype, category, amount, date_iso, notes)
                inserted += 1
            st.success(f"Imported {inserted} rows.")
            st.rerun()
        except Exception as e:
            st.error(f"Import failed: {e}")

# -------------------------
# Settings tab
# -------------------------
with tabs[4]:
    st.header("⚙️ Settings & Members")
    st.subheader("Members")
    members = get_members()
    if members:
        dfm = pd.DataFrame([dict(m) for m in members])
        st.dataframe(dfm)
    else:
        st.info("No members yet. Use the sidebar Sign-in to create one.")

    st.markdown("### Create new member")
    new_user = st.text_input("username for new member", key="new_user")
    new_disp = st.text_input("display name (optional)", key="new_disp")
    if st.button("Create member"):
        if not new_user.strip():
            st.error("username required")
        else:
            add_member(new_user.strip(), new_disp.strip() or None)
            st.success("Member created")
            st.rerun()


    st.markdown("---")
    st.subheader("Budgets")
    for r in get_members():
        b = get_budget(r["id"])
        current = b["monthly_budget"] if b else 0
        st.write(f"**{r['display_name'] or r['username']}** — current budget: ₹{current:,.0f}")
        new_b = st.number_input(f"Set monthly budget (₹) for {r['username']}", min_value=0.0, value=float(current or 0.0), key=f"bud_{r['id']}")
        if st.button(f"Save budget {r['id']}", key=f"save_bud_{r['id']}"):
            set_budget(r["id"], float(new_b))
            st.success("Saved")
            st.rerun()


st.markdown("---")
st.caption("Do not save what is left after spending, but spend what is left after saving.")