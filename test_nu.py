import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from core import Store
from nu_pdf import parse_texts

HEADER = '''Tarjeta de Crédito Nu
Periodo: 18 SEP 2026 al 17 OCT 2026
Fecha límite de pago1: Miércoles, 28 OCT 2026
Pago para no generar intereses2:
 $220.00
Cargos regulares (no a meses) + $220.00
Cargos y compras a meses (capital)7 + $0.00'''
DETAIL = '''CARGOS, ABONOS Y COMPRAS REGULARES (NO A MESES)
01 OCT 2026 02 OCT 2026 Comercio | RFC: S.I. +$100.00
01 OCT 2026 02 OCT 2026 Comercio | RFC: S.I. +$100.00
02 OCT 2026 03 OCT 2026 Otro
comercio | RFC: S.I. +$20.00
03 OCT 2026 04 OCT 2026 Abono de "Comercio" | RFC: S.I. -$10.00
04 OCT 2026 05 OCT 2026 ¡Gracias por tu pago! | RFC: S.I. -$200.00
Total de cargos +$220.00
Total de abonos -$210.00'''

class NuTests(unittest.TestCase):
    def test_movements(self):
        r=parse_texts([HEADER,DETAIL])
        self.assertEqual(len(r['records']),5)
        self.assertEqual(r['warnings'],[])
        self.assertEqual(r['records'][0]['fecha'],'2026-10-02')
        self.assertEqual(r['records'][0]['fecha_operacion'],'2026-10-01')
        self.assertEqual(r['records'][3]['tipo'],'Reembolso')
        self.assertEqual(r['records'][4]['tipo'],'Transferencia')
        self.assertEqual(r['metadata']['fecha_limite'],'2026-10-28')
    def test_dedupe_and_classification_edit(self):
        rows=parse_texts([HEADER,DETAIL])['records']
        with TemporaryDirectory() as tmp:
            db=Store(Path(tmp)/'test.db')
            self.assertEqual(db.insert(rows),5)
            for r in rows: r['categoria']='Nueva'
            self.assertEqual(db.insert(rows),0)
            self.assertEqual(len(db.movements()),5)
    def test_different_account(self):
        a=parse_texts([HEADER,DETAIL],'A')['records']
        b=parse_texts([HEADER,DETAIL],'B')['records']
        self.assertNotEqual(a[0]['_clave_importacion'],b[0]['_clave_importacion'])
    def test_inconsistent_summary(self):
        r=parse_texts([HEADER.replace('$220.00','$230.00'),DETAIL])
        self.assertTrue(r['warnings'])
    def test_reject_other_document(self):
        with self.assertRaises(ValueError): parse_texts(['Otro documento'])
    def test_unreadable_row(self):
        r=parse_texts([HEADER, DETAIL+'\n10 OCT 2026 11 OCT 2026 Incompleto'])
        self.assertTrue(r['warnings'])
    def test_msi_table_not_duplicated(self):
        r=parse_texts([HEADER,'COMPRAS Y CARGOS DIFERIDOS A MESES SIN INTERESES\n01 OCT 2026 02 OCT 2026 Prueba +$999.00',DETAIL])
        self.assertEqual(len(r['records']),5)
    def test_old_database_migration(self):
        import sqlite3
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db'
            db=sqlite3.connect(path)
            db.execute('CREATE TABLE movements (id INTEGER PRIMARY KEY, fecha TEXT, descripcion TEXT, monto REAL, tipo TEXT, categoria TEXT, cuenta TEXT)')
            db.execute("INSERT INTO movements VALUES(1,'2026-01-01','Anterior',10,'Gasto','Otros','A')")
            db.commit();db.close()
            new=Store(path)
            self.assertEqual(new.movements()[0]['descripcion'],'Anterior')
            self.assertEqual(new.insert(parse_texts([HEADER,DETAIL])['records']),5)

if __name__=='__main__': unittest.main()
