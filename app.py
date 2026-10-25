from pathlib import Path
from datetime import date
import calendar
import io
import os
import hashlib
import pandas as pd
import streamlit as st
from core import Store, TYPES, CATEGORIES, money, paydays, debt_plan

st.set_page_config(page_title='Campa Finanzas', page_icon='💰', layout='wide')
st.markdown('''<style>.stApp{background:#f5f7fb}h1,h2,h3{color:#17364b}div[data-testid="stMetric"]{background:white;border:1px solid #dce5ec;border-radius:14px;padding:18px}</style>''', unsafe_allow_html=True)
path = Path(os.environ.get('CAMPA_DATA_DIR', str(Path(__file__).parent / 'datos')))
path.mkdir(parents=True, exist_ok=True)
store = Store(path / 'finanzas.sqlite3')
cfg = store.settings()

def cash(x):
    return f'${x:,.2f}'

def table(key, columns):
    return pd.DataFrame(cfg.get(key, []), columns=columns)

def validate_table(zdf, numeric):
    records = []
    for row in df.to_dict('records'):
        if not str(row.get('nombre', row.get('categoria', '')) or '').strip():
            raise ValueError('Completa el nombre/categoría de todas las filas o elimina la fila vacía.')
        for key in numeric:
            row[key] = float(row[key])
            if not pd.notna(row[key]) or row[key] < 0:
                raise ValueError('Usa números positivos o cero.')
        records.append(row)
    return records

st.title('💰 Campa Finanzas')
st.caption('Tu mes en perspectiva · ingresos, presupuesto, ahorro y deudas · MXN')
with st.sidebar:
    st.header('Tu espacio')
    today = date.today()
    period = st.date_input('Mes que quieres revisar', date(today.year, today.month, 1))
    page = st.radio('Sección', ['Resumen', 'Movimientos', 'Importar estado', 'Plan mensual', 'Ahorro y deudas', 'Respaldo'])
    st.caption('Datos guardados en tu equipo. Una persona y una moneda: MXN.')

year, month = period.year, period.month
all_rows = store.movements()
df = pd.DataFrame(all_rows, columns=['id', 'fecha', 'descripcion', 'monto', 'tipo', 'categoria', 'cuenta'])
current = df[df.fecha.str.startswith(f'{year}-{month:02}', na=False)].copy()
income = cfg.get('income', {'amount': 0, 'frequency': 'Quincenal (15 y fin de mes)', 'anchor': str(date.today())})
dates = paydays(year, month, income['frequency'], date.fromisoformat(income['anchor']))
estimated = len(dates) * income['amount']
fixed = pd.DataFrame(cfg.get('fixed', []), columns=['nombre', 'categoria', 'monto', 'dia'])
budgets = pd.DataFrame(cfg.get('budgets', []), columns=['categoria', 'monto'])
debts = cfg.get('debts', [])
fixed_total = float(fixed.monto.sum())
budget_total = float(budgets.monto.sum())
minimums = sum(d['pago'] for d in debts if d['saldo'] > 0)
free = estimated - fixed_total - budget_total - minimums

if page == 'Resumen':
    st.subheader(f'Balance de {month:02}/{year}')
    a,b,c,d = st.columns(4)
    a.metric('Ingreso estimado', cash(estimated))
    b.metric('Gastos y presupuestos', cash(fixed_total + budget_total))
    c.metric('Pagos base de deudas', cash(minimums))
    d.metric('Disponible proyectado', cash(free))
    if free < 0:
        st.warning('Tu plan compromete más dinero que el ingreso estimado. Ajusta tus importes antes de asignar ahorro.')
    st.caption('El plan es independiente de los movimientos reales: no suma sueldo recibido + sueldo estimado. Los presupuestos son gastos variables adicionales a los fijos.')
    a,b = st.columns(2)
    with a:
        st.markdown('### Distribución del plan')
        st.bar_chart(pd.DataFrame({'MXN': [fixed_total, budget_total, minimums, max(0, free)]}, index=['Fijos', 'Variables', 'Deudas', 'Disponible']))
    with b:
        st.markdown('### Calendario del plan')
        events = {i: 0.0 for i in range(1, calendar.monthrange(year, month)[1]+1)}
        for day in dates:
            events[day.day] += income['amount']
        for r in cfg.get('fixed', []):
            events[min(int(r['dia']), len(events))] -= r['monto']
        events[len(events)] -= budget_total + minimums
        balance = cfg.get('opening', 0)
        series = []
        for day, amount in events.items():
            balance += amount
            series.append({'Día': day, 'Saldo previsto': balance})
        st.line_chart(pd.DataFrame(series).set_index('Día'))
        st.caption('Saldo inicial del plan + cobros − fijos. Variables y deudas se reservan al cierre; no representa sus fechas reales de pago.')
    st.markdown('### Movimientos reales registrados')
    sums = current.groupby('tipo').monto.sum() if len(current) else {}
    a,b,c = st.columns(3)
    a.metric('Ingresos reales', cash(sums.get('Ingreso', 0)))
    b.metric('Gastos reales', cash(sums.get('Gasto', 0)))
    c.metric('Pagos de deuda reales', cash(sums.get('Pago de deuda', 0)))
    st.caption('Transferencias excluidas de ingresos y gastos. Los datos reflejan únicamente lo registrado; no son el saldo bancario.')
    cats = set(budgets.categoria) | set(fixed.categoria) | set(current[current.tipo == 'Gasto'].categoria)
    comparison = []
    for cat in sorted(cats):
        planned = float(budgets.loc[budgets.categoria == cat, 'monto'].sum() + fixed.loc[fixed.categoria == cat, 'monto'].sum())
        actual = float(current.loc[(current.tipo == 'Gasto') & (current.categoria == cat), 'monto'].sum())
        comparison.append({'Categoría': cat, 'Plan': planned, 'Real': actual, 'Restante': planned-actual})
    if comparison:
        comp = pd.DataFrame(comparison).set_index('Categoría')
        st.bar_chart(comp[['Plan', 'Real']])
        st.dataframe(comp, use_container_width=True)
    else:
        st.info('Empieza en Plan mensual y luego importa o registra movimientos.')

elif page == 'Plan mensual':
    st.subheader('Diseña tu mes')
    st.info('Este plan se repite en todos los meses. El sueldo es por pago; quincenal significa 15 y último día, cada 14 días es una opción distinta.')
    with st.form('plan'):
        a,b,c = st.columns(3)
        amount = a.number_input('Sueldo neto por pago (MXN)', min_value=0.0, value=float(income['amount']))
        choices = ['Semanal', 'Quincenal (15 y fin de mes)', 'Cada 14 días', 'Mensual']
        frequency = b.selectbox('Frecuencia', choices, index=choices.index(income['frequency']))
        anchor = c.date_input('Primer pago (semanal/14 días) o día mensual', date.fromisoformat(income['anchor']))
        opening = st.number_input('Saldo inicial para el calendario del plan', value=float(cfg.get('opening', 0)))
        st.markdown('**Gastos fijos mensuales**')
        f = st.data_editor(fixed, num_rows='dynamic', key='fixed', use_container_width=True)
        st.caption('Día entre 1 y 31. Un día inexistente se ajusta al final del mes.')
        st.markdown('**Presupuestos variables mensuales**')
        b = st.data_editor(budgets, num_rows='dynamic', key='budgets', use_container_width=True)
        st.caption('No repitas un gasto fijo aquí. Puedes usar las mismas categorías para comparar el total con lo real.')
        if st.form_submit_button('Guardar plan', type='primary'):
            try:
                fr = validate_table(f, ['monto', 'dia'])
                br = validate_table(b, ['monto'])
                if any(not 1 <= r['dia'] <= 31 or r['dia'] != int(r['dia']) for r in fr):
                    raise ValueError('El día debe ser entero entre 1 y 31.')
                cfg.update(income={'amount':amount, 'frequency':frequency, 'anchor':str(anchor)}, opening=opening, fixed=fr, budgets=br)
                store.save_settings(cfg)
                st.success('Plan guardado. Abre Resumen para ver el resultado.')
            except (ValueError, TypeError) as e:
                st.error(str(e))

elif page == 'Movimientos':
    st.subheader('Registra y revisa tus movimientos')
    with st.form('manual', clear_on_submit=True):
        a,b,c = st.columns(3)
        day = a.date_input('Fecha')
        desc = b.text_input('Descripción')
        amount = c.number_input('Importe positivo', min_value=0.01, value=100.0)
        a,b,c = st.columns(3)
        kind = a.selectbox('Tipo', TYPES)
        cat = b.selectbox('Categoría', CATEGORIES)
        account = c.text_input('Cuenta', 'Principal')
        if st.form_submit_button('Añadir movimiento'):
            if not desc.strip() or not account.strip():
                st.error('Completa descripción y cuenta.')
            else:
                store.insert([dict(fecha=str(day), descripcion=desc.strip(), monto=amount, tipo=kind, categoria=cat, cuenta=account.strip())], False)
                st.rerun()
    st.caption('Compra con tarjeta: Gasto. Pago posterior de esa tarjeta: Transferencia para no duplicar. Para deudas anteriores al registro, usa Pago de deuda. Mantén este criterio de forma consistente.')
    st.dataframe(current, hide_index=True, use_container_width=True)
    ids = st.multiselect('IDs que quieres eliminar', current.id.tolist())
    if st.button('Eliminar seleccionados', disabled=not ids):
        store.delete(ids)
        st.rerun()
    st.download_button('Exportar movimientos del mes', current.to_csv(index=False).encode('utf-8-sig'), 'movimientos.csv', 'text/csv')

elif page == 'Importar estado':
    st.subheader('Importar CSV o Excel')
    st.caption('Requiere una tabla con fecha, descripción e importe; admite cargo y abono separados. PDF y archivos protegidos no están incluidos.')
    upload = st.file_uploader('Estado de cuenta', type=['csv', 'xlsx'])
    if upload:
        signature = hashlib.sha256(upload.getvalue()).hexdigest()
        if st.session_state.get('upload_signature') != signature:
            st.session_state.pop('preview', None)
            st.session_state.pop('import_errors', None)
            st.session_state['upload_signature'] = signature
        try:
            if upload.name.lower().endswith('.csv'):
                a,b = st.columns(2)
                sep = a.selectbox('Separador', [',', ';', '\t'])
                encoding = b.selectbox('Codificación', ['utf-8-sig', 'latin-1'])
                raw = pd.read_csv(io.BytesIO(upload.getvalue()), sep=sep, encoding=encoding, dtype=str)
            else:
                book = pd.ExcelFile(io.BytesIO(upload.getvalue()))
                sheet = st.selectbox('Hoja', book.sheet_names)
                raw = pd.read_excel(book, sheet_name=sheet, dtype=str)
            st.dataframe(raw.head(8), hide_index=True)
            columns = raw.columns.tolist()
            fc = st.selectbox('Columna fecha', columns)
            dc = st.selectbox('Columna descripción', columns, index=min(1,len(columns)-1))
            mode = st.radio('Formato de importes', ['Una columna con signo', 'Cargo y abono separados'])
            decimal = st.selectbox('Separador decimal', ['.', ','])
            fmt = st.selectbox('Formato de fecha', ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y', '%d-%m-%Y'])
            account = st.text_input('Cuenta de estos movimientos', 'Principal')
            if mode == 'Una columna con signo':
                mc = st.selectbox('Importe', columns, index=min(2,len(columns)-1))
                positive_income = st.checkbox('Positivos son ingresos y negativos son gastos', value=True)
            else:
                charge = st.selectbox('Cargo', columns)
                credit = st.selectbox('Abono', columns, index=min(1,len(columns)-1))
            if st.button('Preparar revisión'):
                records, errors = [], []
                for idx, r in raw.iterrows():
                    try:
                        day = pd.to_datetime(r[fc], format=fmt, errors='raise').date()
                        if pd.isna(day) or pd.isna(r[dc]) or not str(r[dc]).strip():
                            raise ValueError('Fecha o descripción vacía')
                        if mode == 'Una columna con signo':
                            value = money(r[mc], decimal) * (1 if positive_income else -1)
                        else:
                            def optional(v):
                                return 0 if pd.isna(v) or not str(v).strip() else money(v, decimal)
                            debit, deposit = optional(r[charge]), optional(r[credit])
                            if debit < 0 or deposit < 0 or (debit and deposit):
                                raise ValueError('Cargo/abono deben ser positivos y solo uno por fila')
                            value = deposit-debit
                        if value == 0:
                            raise ValueError('Importe cero')
                        records.append(dict(fecha=str(day), descripcion=str(r[dc]), monto=abs(value), tipo='Ingreso' if value>0 else 'Gasto', categoria='Otros', cuenta=account))
                    except (ValueError, TypeError) as e:
                        errors.append(f'Fila {idx+2}: {e}')
                st.session_state['preview'] = records
                st.session_state['import_errors'] = errors
            for error in st.session_state.get('import_errors', []):
                st.error(error)
            if st.session_state.get('preview'):
                st.info('Revisa TODAS las filas: clasifica transferencias y pagos de tarjeta antes de confirmar. Las filas inválidas no se incluyen.')
                edited = st.data_editor(pd.DataFrame(st.session_state['preview']), hide_index=True, use_container_width=True, column_config={'tipo':st.column_config.SelectboxColumn(options=TYPES, required=True)})
                skip = st.checkbox('Omitir coincidencias exactas ya guardadas', True)
                st.caption('La coincidencia usa fecha, descripción, importe, tipo, categoría y cuenta. Desactiva esta opción si son operaciones legítimas idénticas; un cambio de clasificación puede permitir duplicados.')
                if st.button('Confirmar y guardar', type='primary'):
                    records = edited.to_dict('records')
                    for r in records:
                        date.fromisoformat(str(r['fecha']))
                        if r['tipo'] not in TYPES or not pd.notna(r['monto']) or float(r['monto']) <= 0 or any(not str(r[k] or '').strip() for k in ['cuenta','descripcion','categoria']):
                            raise ValueError('Revisa tipos, importes y campos vacíos.')
                    n = store.insert(records, skip)
                    st.session_state.pop('preview', None)
                    st.success(f'{n} movimientos guardados. Abre Movimientos para revisarlos.')
        except Exception as e:
            st.error(f'No se pudo procesar: {e}')

elif page == 'Ahorro y deudas':
    st.subheader('Tus próximos objetivos')
    st.metric('Disponible mensual según el plan', cash(free))
    with st.form('debts'):
        st.markdown('**Deudas: tasa nominal anual en %, pago mensual base y saldo actual**')
        dd = st.data_editor(table('debts', ['nombre','saldo','tasa','pago']), num_rows='dynamic', key='debts_table', use_container_width=True)
        if st.form_submit_button('Guardar deudas'):
            try:
                cfg['debts'] = validate_table(dd, ['saldo','tasa','pago'])
                store.save_settings(cfg)
                st.rerun()
            except (ValueError, TypeError) as e:
                st.error(str(e))
    a,b = st.columns(2)
    with a:
        st.markdown('### Meta de ahorro')
        with st.form('goal'):
            goal = cfg.get('goal', {})
            name = st.text_input('Meta', goal.get('name','Fondo de emergencia'))
            target = st.number_input('Monto objetivo', min_value=0.0, value=float(goal.get('target',10000)))
            saved = st.number_input('Ya ahorrado', min_value=0.0, value=float(goal.get('saved',0)))
            contribution = st.number_input('Aportación mensual', min_value=0.0, value=float(goal.get('contribution',0)))
            if st.form_submit_button('Guardar meta'):
                cfg['goal'] = dict(name=name,target=target,saved=saved,contribution=contribution)
                store.save_settings(cfg)
        remaining = max(0, target-saved)
        if target:
            st.progress(min(1.0, saved/target))
        if remaining == 0:
            st.success('Meta alcanzada.')
        elif contribution > 0:
            import math
            months_needed = math.ceil(remaining/contribution)
            st.write(f'Plazo estimado: **{months_needed} meses**, sin rendimientos.')
            horizon = min(months_needed, 120)
            st.line_chart(pd.DataFrame({'Mes':range(horizon+1), 'Ahorro':[min(target,saved+i*contribution) for i in range(horizon+1)]}).set_index('Mes'))
        else:
            st.info('Define una aportación para calcular el plazo.')
    with b:
        st.markdown('### Plan de pago')
        strategy = st.selectbox('Prioridad', ['Avalancha', 'Bola de nieve'])
        st.caption('Avalancha: mayor tasa primero. Bola de nieve: menor saldo primero. El pago total se conserva cuando se liquida una deuda.')
        extra = st.number_input('Pago adicional mensual total', min_value=0.0, value=0.0)
        if contribution + extra > max(0,free):
            st.warning('El ahorro y el pago extra superan el disponible del plan.')
        history = debt_plan(debts, extra, strategy)
        if history:
            result = pd.DataFrame(history)
            st.line_chart(result.set_index('Mes')[['Saldo']])
            if history[-1]['Saldo'] <= .005:
                st.success(f'Liquidación en {len(history)} meses. Intereses estimados: {cash(result.Intereses.sum())}.')
            else:
                st.warning('No se liquida dentro de 360 meses con estos pagos.')
            st.download_button('Descargar plan de deuda', result.to_csv(index=False).encode(), 'plan_deuda.csv')
        else:
            st.info('Añade una deuda con saldo para simular.')
    st.caption('Simulación: interés mensual = saldo × tasa nominal anual / 12. Pagos al cierre, sin comisiones, IVA, seguros ni compras nuevas. No reproduce el cálculo contractual del banco. Actualiza los saldos manualmente; importar un pago no los modifica.')

else:
    st.subheader('Respaldo de tus datos')
    st.write('Guarda una copia de la base de datos y los movimientos. Para restaurar: cierra la app y sustituye datos/finanzas.sqlite3 por tu respaldo.')
    st.download_button('Descargar base de datos completa', (path/'finanzas.sqlite3').read_bytes(), 'finanzas.sqlite3', 'application/octet-stream')
    st.download_button('Exportar todos los movimientos', df.to_csv(index=False).encode('utf-8-sig'), 'todos_movimientos.csv', 'text/csv')
    st.caption('La base local no está cifrada. Conserva los respaldos en una ubicación privada. No se conectan cuentas bancarias ni servicios de IA.')
