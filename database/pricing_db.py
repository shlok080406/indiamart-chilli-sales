import sqlite3
from pathlib import Path
from datetime import datetime


# =========================================================
# DATABASE SETUP
# =========================================================

ROOT = Path(__file__).resolve().parent.parent
DB_FILE = ROOT / "data" / "chilli_sales.db"


def get_connection():
    """Create a connection to the SQLite database."""
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


# =========================================================
# DATABASE MIGRATION
# =========================================================

def add_column_if_missing(connection, table_name, column_name, column_definition):
    """Add a column if it does not already exist."""

    cursor = connection.cursor()

    cursor.execute(f"PRAGMA table_info({table_name})")

    existing_columns = {
        row["name"]
        for row in cursor.fetchall()
    }

    if column_name not in existing_columns:
        cursor.execute(
            f"""
            ALTER TABLE {table_name}
            ADD COLUMN {column_name} {column_definition}
            """
        )


# =========================================================
# CREATE TABLES
# =========================================================

def initialize_database():
    """Create and upgrade the pricing database."""

    connection = get_connection()
    cursor = connection.cursor()

    # -----------------------------------------------------
    # ACTIVE PRICES
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            market_cost REAL NOT NULL,
            processing_cost REAL DEFAULT 0,
            packaging_cost REAL DEFAULT 0,
            other_cost REAL DEFAULT 0,
            margin_percent REAL NOT NULL,
            min_selling_price REAL,
            max_selling_price REAL,
            selling_price REAL NOT NULL,
            price_type TEXT NOT NULL DEFAULT 'Domestic',
            source TEXT,
            effective_from TEXT NOT NULL,
            verified_on TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    # -----------------------------------------------------
    # PRICE HISTORY
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            market_cost REAL NOT NULL,
            processing_cost REAL DEFAULT 0,
            packaging_cost REAL DEFAULT 0,
            other_cost REAL DEFAULT 0,
            margin_percent REAL NOT NULL,
            min_selling_price REAL,
            max_selling_price REAL,
            selling_price REAL NOT NULL,
            price_type TEXT NOT NULL DEFAULT 'Domestic',
            source TEXT,
            effective_from TEXT NOT NULL,
            verified_on TEXT NOT NULL
        )
        """
    )

    # -----------------------------------------------------
    # LEADS / ENQUIRIES
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            company TEXT,
            phone TEXT,
            email TEXT,
            location TEXT,
            delivery_address TEXT,
            requirement TEXT,
            product_id TEXT,
            quantity_kg REAL,
            quoted_price REAL,
            status TEXT NOT NULL DEFAULT 'New',
            created_at TEXT NOT NULL,
            last_contacted TEXT,
            next_follow_up TEXT,
            notes TEXT,
            enquiry_raw_text TEXT,
            parsed_variety TEXT,
            parsed_quantity REAL,
            parsed_location TEXT,
            synced_at TEXT,
            is_parsed INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    # -----------------------------------------------------
    # PRICING TIERS
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_tiers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            min_qty REAL NOT NULL,
            max_qty REAL,
            rate_per_kg REAL NOT NULL,
            UNIQUE(product_id, min_qty)
        )
        """
    )

    # -----------------------------------------------------
    # QUOTATION HISTORY
    # -----------------------------------------------------

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quotation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            quotation_no TEXT NOT NULL,
            customer TEXT NOT NULL,
            product_id TEXT NOT NULL,
            quantity_kg REAL NOT NULL,
            rate_per_kg REAL NOT NULL,
            total_value REAL NOT NULL,
            channel TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'sent'
        )
        """
    )

    # -----------------------------------------------------
    # MIGRATE EXISTING DATABASES
    # -----------------------------------------------------
    #
    # If chilli_sales.db already existed before these
    # columns were added, CREATE TABLE IF NOT EXISTS will
    # NOT add them. So we explicitly check and add them.
    #

    add_column_if_missing(
        connection,
        "prices",
        "min_selling_price",
        "REAL",
    )

    add_column_if_missing(
        connection,
        "prices",
        "max_selling_price",
        "REAL",
    )

    add_column_if_missing(
        connection,
        "price_history",
        "min_selling_price",
        "REAL",
    )

    add_column_if_missing(
        connection,
        "price_history",
        "max_selling_price",
        "REAL",
    )

    # Migrate leads table columns (for JSON-based migration)
    add_column_if_missing(connection, "leads", "company", "TEXT")
    add_column_if_missing(connection, "leads", "phone", "TEXT")
    add_column_if_missing(connection, "leads", "email", "TEXT")
    add_column_if_missing(connection, "leads", "requirement", "TEXT")
    add_column_if_missing(connection, "leads", "product_id", "TEXT")
    add_column_if_missing(connection, "leads", "quoted_price", "REAL")
    add_column_if_missing(connection, "leads", "created_at", "TEXT")
    add_column_if_missing(connection, "leads", "last_contacted", "TEXT")
    add_column_if_missing(connection, "leads", "next_follow_up", "TEXT")
    add_column_if_missing(connection, "leads", "notes", "TEXT")
    add_column_if_missing(connection, "leads", "enquiry_raw_text", "TEXT")
    add_column_if_missing(connection, "leads", "parsed_variety", "TEXT")
    add_column_if_missing(connection, "leads", "parsed_quantity", "REAL")
    add_column_if_missing(connection, "leads", "parsed_location", "TEXT")
    add_column_if_missing(connection, "leads", "synced_at", "TEXT")
    add_column_if_missing(connection, "leads", "is_parsed", "INTEGER DEFAULT 0")

    connection.commit()
    connection.close()


# =========================================================
# SAVE PRICE
# =========================================================

def save_price(
    product_id,
    market_cost,
    processing_cost,
    packaging_cost,
    other_cost,
    margin_percent,
    selling_price,
    price_type,
    source,
    effective_from,
    min_selling_price=None,
    max_selling_price=None,
):
    """
    Save a new price.

    The previous active price is copied into price_history.
    The previous price is then deactivated.
    The new price becomes the active price.
    """

    connection = get_connection()
    cursor = connection.cursor()

    verified_on = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # -----------------------------------------------------
    # MOVE EXISTING ACTIVE PRICE TO HISTORY
    # -----------------------------------------------------

    cursor.execute(
        """
        SELECT *
        FROM prices
        WHERE product_id = ?
        AND is_active = 1
        """,
        (product_id,),
    )

    old_prices = cursor.fetchall()

    for old in old_prices:

        cursor.execute(
            """
            INSERT INTO price_history (
                product_id,
                market_cost,
                processing_cost,
                packaging_cost,
                other_cost,
                margin_percent,
                min_selling_price,
                max_selling_price,
                selling_price,
                price_type,
                source,
                effective_from,
                verified_on
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                old["product_id"],
                old["market_cost"],
                old["processing_cost"],
                old["packaging_cost"],
                old["other_cost"],
                old["margin_percent"],
                old["min_selling_price"],
                old["max_selling_price"],
                old["selling_price"],
                old["price_type"],
                old["source"],
                old["effective_from"],
                old["verified_on"],
            ),
        )

    # -----------------------------------------------------
    # DEACTIVATE OLD PRICES
    # -----------------------------------------------------

    cursor.execute(
        """
        UPDATE prices
        SET is_active = 0
        WHERE product_id = ?
        """,
        (product_id,),
    )

    # -----------------------------------------------------
    # INSERT NEW ACTIVE PRICE
    # -----------------------------------------------------

    cursor.execute(
        """
        INSERT INTO prices (
            product_id,
            market_cost,
            processing_cost,
            packaging_cost,
            other_cost,
            margin_percent,
            min_selling_price,
            max_selling_price,
            selling_price,
            price_type,
            source,
            effective_from,
            verified_on,
            is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            product_id,
            market_cost,
            processing_cost,
            packaging_cost,
            other_cost,
            margin_percent,
            min_selling_price,
            max_selling_price,
            selling_price,
            price_type,
            source,
            effective_from,
            verified_on,
        ),
    )

    connection.commit()
    connection.close()


# =========================================================
# GET CURRENT PRICE
# =========================================================

def get_current_price(product_id):
    """Return the currently active price for a product."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM prices
        WHERE product_id = ?
        AND is_active = 1
        ORDER BY id DESC
        LIMIT 1
        """,
        (product_id,),
    )

    result = cursor.fetchone()

    connection.close()

    return dict(result) if result else None


# =========================================================
# GET PRICE HISTORY
# =========================================================

def get_price_history(product_id):
    """Return previous prices for a product."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM price_history
        WHERE product_id = ?
        ORDER BY id DESC
        """,
        (product_id,),
    )

    results = cursor.fetchall()

    connection.close()

    return [dict(row) for row in results]


# =========================================================
# LEAD / ENQUIRY FUNCTIONS
# =========================================================

def insert_lead(lead_data: dict) -> int:
    """Insert a new lead/ enquiry into the database. Returns the new lead id."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO leads (
            customer, company, phone, email, location,
            delivery_address, requirement, product_id, quantity_kg,
            quoted_price, status, created_at, last_contacted,
            next_follow_up, notes, enquiry_raw_text, parsed_variety,
            parsed_quantity, parsed_location, synced_at, is_parsed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            lead_data.get("customer", ""),
            lead_data.get("company"),
            lead_data.get("phone"),
            lead_data.get("email"),
            lead_data.get("location"),
            lead_data.get("delivery_address"),
            lead_data.get("requirement"),
            lead_data.get("product_id"),
            lead_data.get("quantity_kg"),
            lead_data.get("quoted_price"),
            lead_data.get("status", "New"),
            lead_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            lead_data.get("last_contacted"),
            lead_data.get("next_follow_up"),
            lead_data.get("notes"),
            lead_data.get("enquiry_raw_text"),
            lead_data.get("parsed_variety"),
            lead_data.get("parsed_quantity"),
            lead_data.get("parsed_location"),
            lead_data.get("synced_at"),
            lead_data.get("is_parsed", 0),
        ),
    )

    lead_id = cursor.lastrowid
    connection.commit()
    connection.close()
    return lead_id


def get_unread_leads():
    """Return leads not yet parsed."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM leads WHERE is_parsed = 0 ORDER BY created_at DESC
        """,
    )

    results = cursor.fetchall()
    connection.close()
    return [dict(row) for row in results]


def get_all_leads():
    """Return all leads ordered by created_at descending."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM leads ORDER BY created_at DESC
        """,
    )

    results = cursor.fetchall()
    connection.close()
    return [dict(row) for row in results]


def update_lead_status(lead_id: int, status: str, next_follow_up: str = None):
    """Update lead status and optional next follow-up date."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE leads SET status = ?, next_follow_up = ?, last_contacted = ? WHERE id = ?
        """,
        (
            status,
            next_follow_up,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            lead_id,
        ),
    )

    connection.commit()
    connection.close()


# =========================================================
# PRICING TIERS FUNCTIONS
# =========================================================

def save_tiers(product_id: str, tiers: list):
    """Replace all tiers for a product with a new list."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "DELETE FROM pricing_tiers WHERE product_id = ?",
        (product_id,),
    )

    for tier in tiers:
        cursor.execute(
            """
            INSERT INTO pricing_tiers (product_id, min_qty, max_qty, rate_per_kg)
            VALUES (?, ?, ?, ?)
            """,
            (
                product_id,
                tier["min_qty"],
                tier.get("max_qty"),
                tier["rate_per_kg"],
            ),
        )

    connection.commit()
    connection.close()


def get_tiers_for_product(product_id: str):
    """Return all tiers for a product sorted by min_qty."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM pricing_tiers
        WHERE product_id = ?
        ORDER BY min_qty ASC
        """,
        (product_id,),
    )

    results = cursor.fetchall()
    connection.close()
    return [dict(row) for row in results]


def get_tier_for_quantity(product_id: str, quantity: float):
    """Return the applicable tier for a given quantity."""

    tiers = get_tiers_for_product(product_id)

    for tier in tiers:
        min_qty = tier["min_qty"]
        max_qty = tier.get("max_qty")

        if max_qty is None or quantity <= max_qty:
            return tier

    return None


def get_all_tiers():
    """Return all tiers grouped by product_id."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM pricing_tiers ORDER BY product_id, min_qty ASC
        """,
    )

    results = cursor.fetchall()
    connection.close()
    return [dict(row) for row in results]


# =========================================================
# QUOTATION HISTORY FUNCTIONS
# =========================================================

def save_quotation(quotation_data: dict) -> int:
    """Log a sent quotation in the history."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO quotation_history (
            lead_id, quotation_no, customer, product_id,
            quantity_kg, rate_per_kg, total_value, channel, sent_at, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            quotation_data.get("lead_id"),
            quotation_data.get("quotation_no"),
            quotation_data.get("customer"),
            quotation_data.get("product_id"),
            quotation_data.get("quantity_kg"),
            quotation_data.get("rate_per_kg"),
            quotation_data.get("total_value"),
            quotation_data.get("channel"),
            quotation_data.get("sent_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            quotation_data.get("status", "sent"),
        ),
    )

    qid = cursor.lastrowid
    connection.commit()
    connection.close()
    return qid


def get_quotation_history():
    """Return all sent quotations ordered by sent_at descending."""

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT * FROM quotation_history ORDER BY sent_at DESC
        """,
    )

    results = cursor.fetchall()
    connection.close()
    return [dict(row) for row in results]


# =========================================================
# INITIALIZE DATABASE
# =========================================================

if __name__ == "__main__":

    initialize_database()

    print(
        "Chilli pricing database initialized successfully."
    )

    print(
        f"Database location: {DB_FILE}"
    )