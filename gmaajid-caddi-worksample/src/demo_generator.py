"""Generate synthetic demo CSVs from M&A registry and test scenarios.

Creates orders, inspections, and RFQs with supplier names from test scenarios,
ensuring temporal consistency with M&A event dates.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yaml

from src.ma_registry import MARegistry

PARTS = [
    ("HX-5520", "Aluminum Heat Exchanger", 800.0, 1200.0),
    ("CTRL-9985", "PLC Control Module", 350.0, 500.0),
    ("FAN-2436", "36 inch Axial Fan", 180.0, 280.0),
    ("BRKT-1005", "Heavy Duty Mount", 15.0, 30.0),
    ("DAMPER-3305", "Pneumatic Damper 36 inch", 200.0, 350.0),
    ("BEARING-9905", "Heavy Duty Bearing Set", 60.0, 100.0),
    ("PANEL-8820", "Stainless Control Panel", 220.0, 320.0),
    ("SENSOR-4401", "Temperature Sensor Probe", 40.0, 80.0),
]


def load_test_scenarios(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("scenarios", [])


def generate_demo_data(
    registry: MARegistry,
    scenarios_path: Path,
    output_dir: Path,
    orders_per_scenario: int = 4,
    seed: int = 42,
) -> dict[str, Path]:
    random.seed(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = load_test_scenarios(scenarios_path)

    # Build map: resulting_name -> event_date for temporal consistency
    event_dates: dict[str, str] = {}
    for event in registry.events:
        for rn in event.get("resulting_names", []):
            event_dates[rn["name"]] = event["date"]

    # Generate orders
    orders = []
    order_num = 1
    for sc in scenarios:
        name = sc["input_name"]
        min_date = event_dates.get(name, "2021-10-01")
        for _ in range(orders_per_scenario):
            base = datetime.strptime(min_date, "%Y-%m-%d")
            offset = random.randint(1, 180)
            order_date = base + timedelta(days=offset)
            promised = order_date + timedelta(days=random.randint(14, 60))
            delivered = promised + timedelta(days=random.randint(-5, 15))
            part = random.choice(PARTS)
            qty = random.randint(10, 300)
            price = round(random.uniform(part[2], part[3]), 2)
            orders.append({
                "order_id": f"PO-DEMO-{order_num:03d}",
                "supplier_name": name,
                "part_number": part[0],
                "part_description": part[1],
                "order_date": order_date.strftime("%Y-%m-%d"),
                "promised_date": promised.strftime("%Y-%m-%d"),
                "actual_delivery_date": delivered.strftime("%Y-%m-%d"),
                "quantity": qty,
                "unit_price": price,
                "po_amount": round(qty * price, 2),
            })
            order_num += 1

    orders_df = pd.DataFrame(orders)
    orders_path = output_dir / "demo_orders.csv"
    orders_df.to_csv(orders_path, index=False)

    # Generate inspections
    inspections = []
    insp_num = 1
    for _, order in orders_df.iterrows():
        if random.random() < 0.5:
            continue
        parts_inspected = random.randint(5, int(order["quantity"]))
        reject_rate = random.uniform(0, 0.15)
        parts_rejected = int(parts_inspected * reject_rate)
        reasons = ["Passed", "Surface scratches", "Dimensional error", "Weld porosity", "Sensor drift"]
        reason = "Passed" if parts_rejected == 0 else random.choice(reasons[1:])
        inspections.append({
            "inspection_id": f"INS-DEMO-{insp_num:03d}",
            "order_id": order["order_id"],
            "inspection_date": order["actual_delivery_date"],
            "parts_inspected": parts_inspected,
            "parts_rejected": parts_rejected,
            "rejection_reason": reason,
            "rework_required": "Yes" if parts_rejected > 0 and random.random() < 0.5 else "No",
        })
        insp_num += 1

    insp_df = pd.DataFrame(inspections)
    insp_path = output_dir / "demo_inspections.csv"
    insp_df.to_csv(insp_path, index=False)

    # Generate RFQs
    rfqs = []
    rfq_num = 1
    for sc in scenarios:
        if random.random() < 0.3:
            continue
        part = random.choice(PARTS)
        name = sc["input_name"]
        min_date = event_dates.get(name, "2021-10-01")
        base = datetime.strptime(min_date, "%Y-%m-%d")
        quote_date = base + timedelta(days=random.randint(1, 90))
        rfqs.append({
            "rfq_id": f"RFQ-DEMO-{rfq_num:03d}",
            "supplier_name": name,
            "part_description": part[1],
            "quote_date": quote_date.strftime("%Y-%m-%d"),
            "quoted_price": round(random.uniform(part[2], part[3] * 1.2), 2),
            "lead_time_weeks": random.randint(2, 12),
            "notes": f"Demo scenario {sc['id']} (tier {sc['difficulty']})",
        })
        rfq_num += 1

    rfq_df = pd.DataFrame(rfqs)
    rfq_path = output_dir / "demo_rfq.csv"
    rfq_df.to_csv(rfq_path, index=False)

    return {
        "demo_orders.csv": orders_path,
        "demo_inspections.csv": insp_path,
        "demo_rfq.csv": rfq_path,
    }
