import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class DataLoader:

    def __init__(self, data_dir: str = "./data", db_path: str = None):
        """Initialize DataLoader with smart path detection for Docker and local"""

        # Auto-detect data directory
        if data_dir is None or data_dir == "./data":
            possible_paths = [
                "/app/data",      # Docker
                "./data",         # Local
                "../data",
                "../../data",
            ]
            for path in possible_paths:
                if Path(path).exists():
                    data_dir = path
                    logger.info(f"Found data directory: {data_dir}")
                    break
            if db_path is None:
                db_path = str(Path(data_dir) / "app.db")
                logger.warning("Data directory not found in common paths, using: ./data")

        # Auto-detect database path
        if db_path is None:
            db_path = "/app/data/app.db"
            logger.info("Using database path: /app/data/app.db")

        self.data_dir = Path(data_dir)
        self.db_path = db_path
        self.conn = None
        self._initialized = False
        self.initialize()
    
    def initialize(self):
        """Initialize database loading CSV only once"""
        try:
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"Data directory: {self.data_dir}")
            logger.info(f"Database path: {self.db_path}")

            self.conn = sqlite3.connect(self.db_path)
            logger.info(f"SQLite connection successful")
            self.conn.row_factory = sqlite3.Row

            if not self._check_if_loaded():
                self._load_csv_data()
                self._initialized = True
                logger.info("CSV loaded into SQLite...")
            else:
                logger.info("Using existing database...")
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
    
    def _check_if_loaded(self):
        """Check if data is already in DB"""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM leads")
            count = cursor.fetchone()[0]
            logger.info(f"Database check: found {count} leads")
            return count > 0
        except Exception as e:
            logger.warning(f"Check failed: {e}")
            return False
        
    def _load_csv_data(self):
        """Load from CSV files into SQLite (one time only)"""
        try:
            logger.info(f"Loading CSV files from: {self.data_dir}")

            #read csv files
            leads_df = pd.read_csv(self.data_dir / "leads.csv")
            deals_df = pd.read_csv(self.data_dir / "deals.csv")
            activities_df = pd.read_csv(self.data_dir / "activities.csv")
            orders_df = pd.read_csv(self.data_dir / "orders.csv")

            logger.info(f"CSV files loaded successfully")
            logger.info(f"Leads: {len(leads_df)}, Deals: {len(deals_df)}, Activities: {len(activities_df)}, Orders: {len(orders_df)}")
            
            # replace tables
            leads_df.to_sql("leads", self.conn, if_exists="replace", index=False)
            deals_df.to_sql("deals", self.conn, if_exists="replace", index=False)
            activities_df.to_sql("activities", self.conn, if_exists="replace", index=False)
            orders_df.to_sql("orders", self.conn, if_exists="replace", index=False)

            self.conn.commit()
            print(f"Data loaded into SQLite database: {self.db_path}")
            print(f"Leads: {len(leads_df)}, Deals: {len(deals_df)}, Activities: {len(activities_df)}, Orders: {len(orders_df)}")

            logger.info(f"Data successfully loaded into {self.db_path}")

        except FileNotFoundError as e:
            logger.error(f"CSV file not found: {e}")
            print(f"Error: CSV file not found: {e}")
            print(f"Looking for files in: {self.data_dir.absolute()}")
        except Exception as e:
            logger.error(f"Error loading CSV data: {e}")
            print(f"Error loading CSV data: {e}")

    def query(self, sql: str, params: tuple = None):
        """Execute a SQL query and return the results as a list of dictionaries."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            print(f"Error executing query: {e}")
            return []
    
    def get_open_deals_by_value(self, min_deal_value: float = 50000):
        """
        Get all open deals above a certain value (not filtered by activity).
        """
        sql = """
        SELECT
            l.lead_id,
            l.first_name,
            l.last_name,
            l.company,
            l.segment,
            d.deal_id,
            d.value_eur,
            d.stage,
            MAX(a.date) as last_activity
        FROM leads l
        LEFT JOIN deals d ON l.lead_id = d.lead_id
        LEFT JOIN activities a ON l.lead_id = a.lead_id
        WHERE CAST(d.value_eur AS REAL) > ?
            AND d.stage NOT IN ('Closed Won', 'Closed Lost')
        GROUP BY l.lead_id, d.deal_id
        ORDER BY CAST(d.value_eur AS REAL) DESC
        """
        return self.query(sql, (min_deal_value,))

    def get_cold_leads_with_deals(self, days: int = 30, min_deal_value: float = 20000):
        """
        Get cold leads (no activity in X days) with open deals > min_deal_value.
        """
        sql = """
        SELECT
            l.lead_id,
            l.first_name,
            l.last_name,
            l.company,
            l.segment,
            d.deal_id,
            d.value_eur,
            d.stage,
            MAX(a.date) as last_activity
        FROM leads l
        LEFT JOIN deals d ON l.lead_id = d.lead_id
        LEFT JOIN activities a ON l.lead_id = a.lead_id
        WHERE CAST(d.value_eur AS REAL) > ?
            AND d.stage NOT IN ('Closed Won', 'Closed Lost')
        GROUP BY l.lead_id, d.deal_id
        HAVING MAX(a.date) IS NULL OR
               CAST((julianday('now') - julianday(MAX(a.date))) AS INTEGER) > ?
        ORDER BY CAST(d.value_eur AS REAL) DESC
        """
        return self.query(sql, (min_deal_value, days))
    
    def get_margins_by_category(self):
        """
        Get gross margins by product category.
        NOTE: SQLite stores numbers from CSV as TEXT, so we CAST to REAL
        """
        sql = """
        SELECT 
            category,
            ROUND(AVG((CAST(unit_price_eur AS REAL) - CAST(unit_cost_eur AS REAL)) / CAST(unit_price_eur AS REAL) * 100), 2) as gross_margin_pct,
            ROUND(SUM(CAST(quantity AS REAL) * CAST(unit_price_eur AS REAL)), 2) as total_revenue,
            COUNT(*) as order_count
        FROM orders
        GROUP BY category
        ORDER BY total_revenue DESC
        """
        return self.query(sql)
    
    def get_low_margin_categories(self, threshold: float = 40.0):
        """Get product categories with margins below the specified threshold."""
        sql = """
        SELECT 
            category,
            ROUND(AVG((CAST(unit_price_eur AS REAL) - CAST(unit_cost_eur AS REAL)) / CAST(unit_price_eur AS REAL) * 100), 2) as gross_margin_pct,
            COUNT(*) as order_count
        FROM orders
        GROUP BY category
        HAVING AVG((CAST(unit_price_eur AS REAL) - CAST(unit_cost_eur AS REAL)) / CAST(unit_price_eur AS REAL) * 100) < ?
        ORDER BY gross_margin_pct ASC
        """
        return self.query(sql, (threshold,))
    
    def close(self):
        """Close database connection"""
        if self.conn:
            try:
                self.conn.close()
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing connection: {e}")