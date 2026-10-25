"""Importación con revisión explícita: PDF Nu, CSV y XLSX."""
import hashlib
import io
from datetime import date
import math
import pandas as pd
import streamlit as st
from core import TYPES, money


def render_import(store):
    st.subheader('Importar estado de cuenta')
    st.caption('PDF de tarjeta Nu, CSV o Excel. El archivo se procesa localmente; nada se guarda hasta confirmar.')
    upload = st.file_uploader('Selecciona tu archivo', type=['pdf','csv','xlsx'])
    if not upload:
        return
    signature = hashlib.sha256(upload.getvalue()).hexdigest()
    if st.session_state.get('import_signature') != signature:
        for key in ['import_preview','import_errors','import_metadata','import_warnings']:
            st.session_state.pop(key,None)
        st.session_state['import_signature'] = signature
    is_pdf = upload.name.lower().endswith('.pdf')
    account = st.text_input('Nombre de la cuenta', 'Nu' if is_pdf else 'Principal')
    try:
        if is_pdf:
            st.info('Nu: los cargos (+) son gastos. Los pagos a la tarjeta son transferencias y los abonos de compras son reembolsos. Revisa la clasificación sugerida.')
            if st.button('Leer PDF de Nu', type='primary'):
                from nu_pdf import parse_pdf
                result = parse_pdf(upload.getvalue(),account)
                st.session_state['import_preview'] = result['records']
                st.session_state['import_metadata'] = result['metadata']
                st.session_state['import_warnings'] = result['warnings']
                st.session_state['import_errors'] = []
        else:
            if upload.name.lower().endswith('.csv'):
                a,b=st.columns(2)
                sep=a.selectbox('Separador',[',',';','\t'])
                encoding=b.selectbox('Codificación',['utf-8-sig','latin-1'])
                raw=pd.read_csv(io.BytesIO(upload.getvalue()),sep=sep,encoding=encoding,dtype=str)
            else:
                book=pd.ExcelFile(io.BytesIO(upload.getvalue()))
                sheet=st.selectbox('Hoja',book.sheet_names)
                raw=pd.read_excel(book,sheet_name=sheet,dtype=str)
            if len(raw.columns)==0: raise ValueError('El archivo no tiene columnas.')
            st.dataframe(raw.head(8),hide_index=True)
            columns=raw.columns.tolist()
            fc=st.selectbox('Columna fecha',columns)
            dc=st.selectbox('Columna descripción',columns,index=min(1,len(columns)-1))
            mode=st.radio('Formato de importes',['Una columna con signo','Cargo y abono separados'])
            decimal=st.selectbox('Separador decimal',['.',','])
            fmt=st.selectbox('Formato de fecha',['%d/%m/%Y','%Y-%m-%d','%m/%d/%Y','%d-%m-%Y'])
            if mode=='Una columna con signo':
                mc=st.selectbox('Importe',columns,index=min(2,len(columns)-1))
                positive_income=st.checkbox('Positivos son ingresos y negativos son gastos',True)
                st.caption('En tarjetas de crédito los cargos pueden ser positivos: desmarca la casilla y reclasifica pagos y reembolsos en la revisión.')
            else:
                charge=st.selectbox('Cargo',columns)
                credit=st.selectbox('Abono',columns,index=min(1,len(columns)-1))
            if st.button('Preparar revisión'):
                if not account.strip(): raise ValueError('Indica una cuenta.')
                records,errors=[],[]
                for idx,r in raw.iterrows():
                    try:
                        day=pd.to_datetime(r[fc],format=fmt,errors='raise').date()
                        if pd.isna(day) or pd.isna(r[dc]) or not str(r[dc]).strip(): raise ValueError('Fecha o descripción vacía')
                        if mode=='Una columna con signo':
                            value=money(r[mc],decimal)*(1 if positive_income else -1)
                        else:
                            def optional(v):
                                return 0 if pd.isna(v) or not str(v).strip() else money(v,decimal)
                            debit,deposit=optional(r[charge]),optional(r[credit])
                            if debit<0 or deposit<0 or (debit and deposit): raise ValueError('Solo un cargo o abono positivo por fila')
                            value=deposit-debit
                        if value==0: raise ValueError('Importe cero')
                        records.append(dict(fecha=str(day),descripcion=str(r[dc]),monto=abs(value),tipo='Ingreso' if value>0 else 'Gasto',categoria='Otros',cuenta=account.strip(),guardar=True))
                    except (ValueError,TypeError) as e:
                        errors.append(f'Fila {idx+2}: {e}')
                st.session_state['import_preview']=records
                st.session_state['import_errors']=errors
                st.session_state.pop('import_metadata',None)
                st.session_state['import_warnings']=[]
        metadata=st.session_state.get('import_metadata',{})
        if metadata:
            st.markdown('**Información del documento**')
            st.write(f"Período: {metadata['inicio_periodo']} al {metadata['fin_periodo']}")
            if 'fecha_limite' in metadata: st.write('Fecha límite de pago: '+metadata['fecha_limite'])
            a,b,c=st.columns(3)
            a.metric('Movimientos detectados',metadata['movimientos'])
            b.metric('Cargos del desglose',f"${metadata['cargos_detectados']:,.2f}")
            c.metric('Abonos del desglose',f"${metadata['abonos_detectados']:,.2f}")
            if 'pago_no_intereses' in metadata: st.write(f"Pago para no generar intereses indicado en el PDF: **${metadata['pago_no_intereses']:,.2f}**")
            st.caption('El período del estado cruza meses. El Resumen agrupa por fecha de cargo; para ver todos los movimientos importados, revisa los meses del período. Los totales del documento son informativos y no crean otra deuda ni otro gasto.')
        for error in st.session_state.get('import_errors',[]): st.error(error)
        warnings=st.session_state.get('import_warnings',[])
        for warning in warnings: st.warning(warning)
        preview=st.session_state.get('import_preview')
        if preview:
            st.markdown('**Revisa antes de guardar**')
            st.caption('Desmarca guardar para excluir una fila. Las categorías son sugerencias. Nu usa la fecha de cargo: una mensualidad no se registra como si hubieras comprado de nuevo el total del producto.')
            edited=st.data_editor(pd.DataFrame(preview),hide_index=True,use_container_width=True,key='review_'+signature,
                disabled=['fecha_operacion','pagina','_clave_importacion'],
                column_config={'tipo':st.column_config.SelectboxColumn(options=TYPES,required=True),'_clave_importacion':None,'guardar':st.column_config.CheckboxColumn(required=True)})
            skip=st.checkbox('Omitir movimientos ya importados',True)
            st.caption('PDF Nu: cada operación tiene una clave que conserva compras idénticas separadas y evita repetir el mismo registro al reimportar, incluso si cambias su categoría. Mantén el mismo nombre de cuenta. CSV/Excel: se omiten coincidencias exactas de todos los campos; revisa operaciones legítimas idénticas.')
            acknowledged=st.checkbox('Revisé las advertencias y quiero continuar') if warnings else True
            if st.button('Confirmar y guardar',type='primary',disabled=not acknowledged):
                records=[]
                for r in edited.to_dict('records'):
                    if not r.get('guardar',True): continue
                    date.fromisoformat(str(r['fecha']))
                    if r['tipo'] not in TYPES or not math.isfinite(float(r['monto'])) or float(r['monto'])<=0:
                        raise ValueError('Revisa el tipo y el importe positivo de cada fila.')
                    for key in ['cuenta','descripcion','categoria']:
                        if pd.isna(r[key]) or not str(r[key]).strip(): raise ValueError('Completa descripción, categoría y cuenta.')
                        r[key]=str(r[key]).strip()
                    r['monto']=round(float(r['monto']),2)
                    records.append(r)
                n=store.insert(records,skip)
                st.success(f'{n} movimientos guardados; {len(records)-n} coincidencias omitidas.')
                st.caption('Puedes volver a confirmar: con omisión activada no se repiten los registros ya importados.')
    except Exception as e:
        st.error(f'No se pudo procesar el archivo: {e}')
