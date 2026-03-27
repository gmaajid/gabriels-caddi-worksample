"""Tests for Pydantic model CSV loader helpers."""

from src.models import (
    build_rfq_to_po_map,
    init_supplier_normalizer,
    load_inspections_from_csv,
    load_orders_from_csv,
    load_rfq_from_csv,
)


def setup_module():
    init_supplier_normalizer([
        "APEX MFG", "Apex Mfg", "APEX Manufacturing Inc", "Apex Manufacturing Inc",
        "AeroFlow Systems", "Precision Thermal Co", "QuickFab Industries",
        "Stellar Metalworks", "TitanForge LLC",
    ])


def test_load_orders_from_csv(tmp_path):
    f = tmp_path / "orders.csv"
    f.write_text(
        "order_id,supplier_name,part_number,part_description,order_date,promised_date,"
        "actual_delivery_date,quantity,unit_price,po_amount\n"
        "PO-2021-011,APEX MFG,CTRL-9998,Controller,2021-10-01,2021-11-12,2021-11-15,10,100.0,1000.0\n"
        "PO-2025-501,Stellar Metalworks,X-001,Part,2025-09-01,2025-10-15,2025-10-15,5,50.0,250.0\n"
    )
    orders = load_orders_from_csv(str(f))
    assert len(orders) == 2
    assert orders[0].order_id == "PO-2021-011"
    assert orders[0].days_late == 3


def test_load_orders_missing_delivery(tmp_path):
    f = tmp_path / "orders.csv"
    f.write_text(
        "order_id,supplier_name,part_number,part_description,order_date,promised_date,"
        "actual_delivery_date,quantity,unit_price,po_amount\n"
        "PO-2025-501,Stellar Metalworks,X-001,Part,2025-09-01,2025-10-15,,5,50.0,250.0\n"
    )
    orders = load_orders_from_csv(str(f))
    assert orders[0].actual_delivery_date is None
    assert orders[0].days_late is None


def test_load_inspections_from_csv(tmp_path):
    f = tmp_path / "inspections.csv"
    f.write_text(
        "inspection_id,order_id,inspection_date,parts_inspected,parts_rejected,rejection_reason,rework_required\n"
        "INS-001,PO-2021-011,2021-11-18,100,5,Burrs on edges,Yes\n"
        "INS-002,PO-2021-011,2021-11-19,50,0,Passed,No\n"
    )
    inspections = load_inspections_from_csv(str(f))
    assert len(inspections) == 2
    assert inspections[0].rework_required is True
    assert inspections[1].rework_required is False
    assert inspections[1].parts_rejected == 0


def test_load_rfq_from_csv(tmp_path):
    f = tmp_path / "rfq.csv"
    f.write_text(
        "rfq_id,supplier_name,part_description,quote_date,quoted_price,lead_time_weeks,notes\n"
        "RFQ-2021-001,APEX MFG,Vibration Mount,2022-02-10,27.4,5,Industrial grade\n"
    )
    responses = load_rfq_from_csv(str(f))
    assert len(responses) == 1
    assert responses[0].quoted_price == 27.4


def test_build_rfq_to_po_map():
    rfq_ids = ["RFQ-2021-001", "RFQ-2021-002", "RFQ-2021-003"]
    order_ids = ["PO-2021-011", "PO-2021-021", "PO-2021-032", "PO-2021-042"]
    mapping = build_rfq_to_po_map(rfq_ids, order_ids)
    assert mapping["RFQ-2021-001"] == "PO-2021-011"
    assert mapping["RFQ-2021-002"] == "PO-2021-021"
    assert mapping["RFQ-2021-003"] == "PO-2021-032"
    assert len(mapping) == 3  # only 3 RFQs, not 4 POs
