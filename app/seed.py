"""Seed the database with realistic offset-printing sample data.

Run with:  python -m app.seed
Idempotent: skips any record whose code already exists.
"""
from .database import Base, SessionLocal, engine
from .models import Customer, FinishingType, Machine, Settings, StockItem, Supplier


def _get_or_create(db, model, code, **values):
    obj = db.query(model).filter(model.code == code).one_or_none()
    if obj:
        return obj, False
    obj = model(code=code, **values)
    db.add(obj)
    return obj, True


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    created = 0

    suppliers = [
        ("SUP-PAPER", dict(name="Apex Paper Mills", phone="03-1234 5678",
                           email="sales@apexpaper.com", payment_terms_days=30)),
        ("SUP-INK", dict(name="ChromaInk Supplies", phone="03-2233 4455",
                         email="orders@chromaink.com", payment_terms_days=45)),
        ("SUP-PLATE", dict(name="PlateTech CTP", phone="03-9988 7766",
                           email="info@platetech.com", payment_terms_days=30)),
    ]
    sup_objs = {}
    for code, vals in suppliers:
        obj, is_new = _get_or_create(db, Supplier, code, **vals)
        sup_objs[code] = obj
        created += is_new
    db.flush()

    customers = [
        ("CUST-001", dict(name="Ahmad Razali", company="Razali Marketing Sdn Bhd",
                          phone="012-345 6789", email="ahmad@razali.com",
                          city="Kuala Lumpur", credit_limit=20000, payment_terms_days=30)),
        ("CUST-002", dict(name="Siti Nurhaliza", company="Bright Events",
                          phone="013-222 3344", email="siti@brightevents.my",
                          city="Shah Alam", credit_limit=10000, payment_terms_days=14)),
        ("CUST-003", dict(name="Walk-in Customer", company="",
                          city="", credit_limit=0, payment_terms_days=0)),
    ]
    for code, vals in customers:
        _, is_new = _get_or_create(db, Customer, code, **vals)
        created += is_new

    papers = [
        ("PPR-ART128", dict(name="Art Paper 128gsm 27×40", category="Paper", unit="Sheet",
                            gsm=128, sheet_width_mm=686, sheet_height_mm=1016,
                            cost_price=0.28, sell_price=0.40, qty_on_hand=8000,
                            reorder_level=2000, supplier_id=sup_objs["SUP-PAPER"].id)),
        ("PPR-ART157", dict(name="Art Paper 157gsm 27×40", category="Paper", unit="Sheet",
                            gsm=157, sheet_width_mm=686, sheet_height_mm=1016,
                            cost_price=0.34, sell_price=0.48, qty_on_hand=6000,
                            reorder_level=2000, supplier_id=sup_objs["SUP-PAPER"].id)),
        ("PPR-ART260", dict(name="Art Card 260gsm 27×40", category="Paper", unit="Sheet",
                            gsm=260, sheet_width_mm=686, sheet_height_mm=1016,
                            cost_price=0.55, sell_price=0.78, qty_on_hand=1500,
                            reorder_level=2000, supplier_id=sup_objs["SUP-PAPER"].id)),
        ("PPR-WD80", dict(name="Woodfree 80gsm 25×38", category="Paper", unit="Sheet",
                          gsm=80, sheet_width_mm=635, sheet_height_mm=965,
                          cost_price=0.18, sell_price=0.27, qty_on_hand=12000,
                          reorder_level=3000, supplier_id=sup_objs["SUP-PAPER"].id)),
        ("INK-CMYK", dict(name="Process Ink CMYK (set)", category="Ink", unit="Kg",
                          cost_price=42.0, sell_price=0, qty_on_hand=60,
                          reorder_level=20, supplier_id=sup_objs["SUP-INK"].id)),
        ("PLT-CTP", dict(name="CTP Plate 1030×790", category="Plate", unit="Pcs",
                         cost_price=12.0, sell_price=0, qty_on_hand=300,
                         reorder_level=100, supplier_id=sup_objs["SUP-PLATE"].id)),
    ]
    for code, vals in papers:
        _, is_new = _get_or_create(db, StockItem, code, **vals)
        created += is_new

    finishing = [
        ("FIN-LAMG", dict(name="Lamination Gloss", pricing_method="per_sqm",
                          unit_rate=1.20, setup_cost=15)),
        ("FIN-LAMM", dict(name="Lamination Matt", pricing_method="per_sqm",
                          unit_rate=1.40, setup_cost=15)),
        ("FIN-UV", dict(name="UV Spot Coating", pricing_method="per_sheet",
                        unit_rate=0.08, setup_cost=80)),
        ("FIN-DIE", dict(name="Die Cutting", pricing_method="per_sheet",
                         unit_rate=0.05, setup_cost=120)),
        ("FIN-SS", dict(name="Saddle Stitch Binding", pricing_method="per_piece",
                        unit_rate=0.12, setup_cost=30)),
        ("FIN-PB", dict(name="Perfect Binding", pricing_method="per_piece",
                        unit_rate=0.45, setup_cost=60)),
        ("FIN-FOLD", dict(name="Folding", pricing_method="per_piece",
                          unit_rate=0.03, setup_cost=20)),
        ("FIN-NUM", dict(name="Numbering", pricing_method="per_piece",
                         unit_rate=0.02, setup_cost=25)),
    ]
    for code, vals in finishing:
        _, is_new = _get_or_create(db, FinishingType, code, **vals)
        created += is_new

    machines = [
        ("MC-SM74", dict(name="Heidelberg SM74 (4-col)", type="Press", max_colors=4,
                         max_sheet_width_mm=740, max_sheet_height_mm=520,
                         hourly_rate=180, makeready_cost=120, makeready_minutes=30,
                         run_rate_per_hour=12000)),
        ("MC-GTO52", dict(name="Heidelberg GTO52 (2-col)", type="Press", max_colors=2,
                          max_sheet_width_mm=520, max_sheet_height_mm=360,
                          hourly_rate=90, makeready_cost=60, makeready_minutes=20,
                          run_rate_per_hour=8000)),
        ("MC-CTP", dict(name="CTP Platesetter", type="CTP", max_colors=0,
                        hourly_rate=70, makeready_cost=0, makeready_minutes=0,
                        run_rate_per_hour=30)),
        ("MC-CUT", dict(name="Polar 115 Guillotine", type="Cutter", max_colors=0,
                        hourly_rate=60, makeready_cost=10, makeready_minutes=5,
                        run_rate_per_hour=0)),
        ("MC-LAM", dict(name="Laminator GMP", type="Laminator", max_colors=0,
                        hourly_rate=55, makeready_cost=15, makeready_minutes=10,
                        run_rate_per_hour=3000)),
    ]
    for code, vals in machines:
        _, is_new = _get_or_create(db, Machine, code, **vals)
        created += is_new

    if not db.get(Settings, 1):
        db.add(Settings(
            id=1,
            company_name="Sample Offset Press Sdn Bhd",
            company_address="No. 12, Jalan Industri 3\n40000 Shah Alam, Selangor",
            company_phone="03-5544 3322",
            company_email="sales@sampleoffset.my",
            currency="RM",
        ))
        created += 1

    # Standard chart of accounts (shared with app startup).
    from .defaults import ensure_standard_accounts
    created += ensure_standard_accounts(db)

    db.commit()
    db.close()
    print(f"Seed complete. {created} new record(s) created.")


if __name__ == "__main__":
    seed()
