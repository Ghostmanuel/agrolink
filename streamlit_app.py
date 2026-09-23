import streamlit as st
import requests

API = st.sidebar.text_input("API", "http://localhost:8000")
if "token" not in st.session_state: st.session_state.token = ""
if "user" not in st.session_state: st.session_state.user = None

st.set_page_config(page_title="AgroLink Angola", page_icon="🌱", layout="wide")
st.title("🌱 AgroLink Angola")
st.caption("Do produtor ao mercado.")

def headers():
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}

tab1, tab2, tab3, tab4 = st.tabs(["Entrar", "Marketplace", "Publicar", "Pedidos"])

with tab1:
    mode = st.radio("Acesso", ["Entrar", "Criar conta"], horizontal=True)
    if mode == "Entrar":
        phone = st.text_input("Telefone")
        password = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            r = requests.post(f"{API}/api/v1/auth/login", json={"phone": phone, "password": password})
            if r.ok:
                data = r.json(); st.session_state.token = data["access_token"]; st.session_state.user = data["user"]
                st.success(f"Bem-vindo, {data['user']['name']}!")
                st.rerun()
            else: st.error(r.json().get("detail", "Erro"))
    else:
        name = st.text_input("Nome")
        phone = st.text_input("Telefone", key="regphone")
        password = st.text_input("Senha", type="password", key="regpass")
        role = st.selectbox("Perfil", ["buyer", "farmer", "driver"])
        province = st.text_input("Província")
        if st.button("Criar conta"):
            r = requests.post(f"{API}/api/v1/auth/register",
                json={"name":name,"phone":phone,"password":password,"role":role,"province":province})
            if r.ok:
                data=r.json(); st.session_state.token=data["access_token"]; st.session_state.user=data["user"]
                st.success("Conta criada."); st.rerun()
            else: st.error(r.json().get("detail", "Erro"))

with tab2:
    st.subheader("Marketplace")
    q = st.text_input("🔎 Procurar produto")
    r = requests.get(f"{API}/api/v1/products", params={"q": q} if q else {})
    if r.ok:
        data = r.json()
        for p in data:
            with st.container(border=True):
                c1,c2,c3 = st.columns([2,2,1])
                c1.write(f"### {p['name']}")
                c1.write(f"{p['category']} · {p['province']}")
                c2.write(f"**Kz {p['price']:,.0f}/{p['unit']}**")
                c2.write(f"Disponível: {p['quantity']:,.0f} {p['unit']}")
                if st.session_state.user and st.session_state.user["role"] == "buyer":
                    qty = c3.number_input("Qtd.", 1.0, float(p["quantity"]), 1.0, key=f"q{p['id']}")
                    if c3.button("Comprar", key=f"b{p['id']}"):
                        rr=requests.post(f"{API}/api/v1/orders",headers=headers(),
                                          json={"product_id":p["id"],"quantity":qty})
                        if rr.ok: st.success(f"Pedido criado. Total: Kz {rr.json()['total']:,.0f}")
                        else: st.error(rr.json().get("detail","Erro"))

with tab3:
    st.subheader("Publicar produção")
    if not st.session_state.user or st.session_state.user["role"] != "farmer":
        st.info("Entre com uma conta de agricultor para publicar.")
    else:
        name=st.text_input("Produto"); category=st.selectbox("Categoria",["Hortícolas","Frutas","Grãos","Raízes","Tubérculos","Outros"])
        price=st.number_input("Preço (Kz)", min_value=1.0); quantity=st.number_input("Quantidade", min_value=1.0)
        unit=st.selectbox("Unidade",["kg","tonelada","saco","caixa","unidade"]); province=st.text_input("Província")
        description=st.text_area("Descrição")
        if st.button("🌱 Publicar"):
            r=requests.post(f"{API}/api/v1/products",headers=headers(),
                            json={"name":name,"category":category,"price":price,"quantity":quantity,
                                  "unit":unit,"province":province,"description":description})
            st.success("Produto publicado!") if r.ok else st.error(r.json().get("detail","Erro"))

with tab4:
    st.subheader("Meus pedidos")
    if not st.session_state.token: st.info("Entre primeiro.")
    else:
        r=requests.get(f"{API}/api/v1/orders",headers=headers())
        if r.ok: st.dataframe(r.json(), use_container_width=True)
        else: st.error(r.json().get("detail","Erro"))
