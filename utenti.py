from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
from datetime import datetime
import secrets
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_sqlalchemy import SQLAlchemy  # ← AGGIUNGI QUESTO
from dotenv import load_dotenv  # ← AGGIUNGI QUESTO

load_dotenv()  # ← AGGIUNGI QUESTO

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_key_change_in_production")

# ======== CONFIGURAZIONE DATABASE PORTABILE ========
import os

# Se siamo su Render, usa SQLite nella cartella corrente
if os.getenv("RENDER") or os.getenv("USE_SQLITE") == "true":
    database_url = "sqlite:///registro.db"  # File SQLite nella cartella dell'app
else:
    # Locale: usa PostgreSQL se configurato, altrimenti SQLite
    database_url = os.getenv("DATABASE_URL", "sqlite:///registro.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Configura engine options solo per database non-SQLite
if not database_url.startswith("sqlite"):
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }

db = SQLAlchemy(app)# ✅ AGGIUNGI QUESTO (funziona su Windows E Linux):
import os
# ═══════════════════════════════════════════════════════════
# CODICE TEMPORANEO: CREA UTENTI DI TEST PER RENDER
# ═══════════════════════════════════════════════════════════
with app.app_context():
    db.create_all()  # Crea le tabelle se non esistono
    
# Usa la variabile d'ambiente RENDER se esiste (su Render), altrimenti percorso locale
if os.getenv("RENDER"):
    # Su Render: usa la cartella corrente per i file JSON (o meglio, usa il database)
    BASE_DIR = os.path.join(os.getcwd(), "data")
else:
    # Locale Windows: il tuo percorso originale
    BASE_DIR = r"C:\Users\andre\OneDrive\Desktop\RegistroProf\registro"

# Crea la cartella se non esiste
os.makedirs(BASE_DIR, exist_ok=True)
FILE_UTENTI = os.path.join(BASE_DIR, "utenti.json")
FILE_VOTI = os.path.join(BASE_DIR, "registro.json")
FILE_RECENSIONI = os.path.join(BASE_DIR, "recensioni.json")
FILE_PROFESSORI = os.path.join(BASE_DIR, "professori.json")
FILE_SESSIONI = os.path.join(BASE_DIR, "sessioni.json")
FILE_SEGNALAZIONI = os.path.join(BASE_DIR, "segnalazioni.json")
FILE_REGISTRAZIONI = os.path.join(BASE_DIR, "registrazioni.json")
FILE_AVVISI = os.path.join(BASE_DIR, "avvisi.json")
FILE_TICKET = os.path.join(BASE_DIR, "ticket.json")
FILE_NOTIFICHE = os.path.join(BASE_DIR, "notifiche.json")
FILE_RECUPERO = os.path.join(BASE_DIR, "recupero_password.json")


# ======== FUNZIONI JSON ========
def leggi_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return []


def scrivi_json(path, dati):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=4)


# ======== CAPTCHA SESSIONE ========
def genera_captcha():
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    return {"domanda": f"{a} + {b} = ?", "risposta": a + b}


# ======== CODICE RECUPERO PASSWORD ========
def genera_codice_recupero():
    return str(random.randint(100000, 999999))


# ======== GESTIONE SESSIONI ========
def genera_session_id():
    return secrets.token_urlsafe(32)


def registra_sessione(username):
    sessioni = leggi_json(FILE_SESSIONI)
    session_id = genera_session_id()
    sessioni = [s for s in sessioni if s["username"] != username]
    
    nuova_sessione = {
        "session_id": session_id,
        "username": username,
        "ip": request.remote_addr or "0.0.0.0",
        "login_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_activity": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_agent": request.headers.get("User-Agent", "Unknown")[:100]
    }
    sessioni.append(nuova_sessione)
    scrivi_json(FILE_SESSIONI, sessioni)
    return session_id


def aggiorna_attivita_sessione():
    if "username" not in session:
        return
    sessioni = leggi_json(FILE_SESSIONI)
    for s in sessioni:
        if s["username"] == session["username"]:
            s["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            break
    scrivi_json(FILE_SESSIONI, sessioni)


def pulisci_sessioni_scadute():
    sessioni = leggi_json(FILE_SESSIONI)
    ora_corrente = datetime.now()
    sessioni_attive = []
    for s in sessioni:
        last_activity = datetime.strptime(s["last_activity"], "%Y-%m-%d %H:%M:%S")
        if (ora_corrente - last_activity).total_seconds() < 86400:
            sessioni_attive.append(s)
    if len(sessioni_attive) != len(sessioni):
        scrivi_json(FILE_SESSIONI, sessioni_attive)


# ======== FUNZIONE CREA NOTIFICA ========
def crea_notifica(username, tipo, titolo, messaggio, link=None):
    notifiche = leggi_json(FILE_NOTIFICHE)
    nuova_notifica = {
        "id": len(notifiche) + 1,
        "utente": username,
        "tipo": tipo,
        "titolo": titolo,
        "messaggio": messaggio,
        "link": link,
        "letta": False,
        "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_lettura": None
    }
    notifiche.append(nuova_notifica)
    scrivi_json(FILE_NOTIFICHE, notifiche)
    return nuova_notifica


# ======== CONFIGURAZIONE EMAIL ========
SMTP_SERVER = "smtp-mail.outlook.com"
SMTP_PORT = 587
EMAIL_SENDER = "assistenzaregistroprof@outlook.com"
EMAIL_PASSWORD = ""  # Inserisci la tua App Password di Outlook
EMAIL_RECEIVER = "assistenzaregistroprof@outlook.com"
SITE_URL = "http://localhost:5000"


def invia_email_ticket(ticket):
    if not EMAIL_PASSWORD:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎫 Nuovo Ticket #{ticket['id']}: {ticket['oggetto']}"
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECEIVER
        ticket_link = f"{SITE_URL}/admin#ticket-{ticket['id']}"
        html = f"""
        <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0; color: white;">
                <h2 style="margin: 0;">🎫 Nuovo Ticket di Supporto</h2>
                <p style="margin: 5px 0 0 0; opacity: 0.9;">Ticket #{ticket['id']}</p>
            </div>
            <div style="background: #f8f9fa; padding: 25px; border: 1px solid #e0e0e0; border-top: none;">
                <p><strong>Utente:</strong> {ticket['utente']}</p>
                <p><strong>Oggetto:</strong> {ticket['oggetto']}</p>
                <p><strong>Messaggio:</strong> {ticket['messaggio']}</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{ticket_link}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 35px; text-decoration: none; border-radius: 25px; font-weight: bold; display: inline-block;">👁️ Visualizza Ticket</a>
                </div>
            </div>
        </body></html>
        """
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"❌ Errore invio email: {e}")
        return False


# =====================================================
# ======================= HOME ========================
# =====================================================

@app.route("/")
def index():
    return redirect(url_for("home"))


@app.route("/home")
def home():
    avvisi = leggi_json(FILE_AVVISI)
    avvisi_attivi = [a for a in avvisi if a.get("attivo", True)]
    return render_template("index.html", avvisi=avvisi_attivi)


# =====================================================
# ======================= LOGIN =======================
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        utenti = leggi_json(FILE_UTENTI)
        
        for user in utenti:
            if user["username"] == username and user["password"] == password:
                # ✅ CONTROLLA STATO REGISTRAZIONE
                if user.get("stato", "attivo") == "in_attesa":
                    return render_template("login.html", error="⏳ Il tuo account è in attesa di approvazione da parte dell'admin.")
                
                # ✅ CONTROLLA STATO ACCOUNT (NUOVO)
                account_status = user.get("account_status", "attivo")
                
                if account_status == "sospeso":
                    return render_template("login.html", 
                        error="⚠️ Il tuo account è SOSPESO. Contatta l'admin per maggiori informazioni.")
                
                if account_status == "bannato":
                    return render_template("login.html", 
                        error="❌ Il tuo account è BANNATO. Non puoi più accedere a questo servizio.")
                
                # ✅ Account attivo - procedi con login
                session["username"] = username
                session["role"] = user.get("role", "user")
                session["session_id"] = genera_session_id()
                registra_sessione(username)
                
                if session["role"] == "admin":
                    return redirect(url_for("admin_dashboard"))
                else:
                    return redirect(url_for("user_dashboard"))
        
        return render_template("login.html", error="Credenziali errate")
    
    return render_template("login.html")

# =====================================================
# ============= RECUPERO PASSWORD =====================
# =====================================================

@app.route("/recupero-password", methods=["GET", "POST"])
def recupero_password():
    if request.method == "POST":
        step = request.form.get("step", "1")
        if step == "1":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            utenti = leggi_json(FILE_UTENTI)
            utente_trovato = None
            for u in utenti:
                if u["username"] == username and u.get("email") == email:
                    utente_trovato = u
                    break
            if not utente_trovato:
                return render_template("recupero_password.html", errore="Username o email non trovati", step=1)
            codice = genera_codice_recupero()
            recupero = {"username": username, "codice": codice, "data_richiesta": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "usato": False}
            recuperi = leggi_json(FILE_RECUPERO)
            recuperi.append(recupero)
            scrivi_json(FILE_RECUPERO, recuperi)
            return render_template("recupero_password.html", step=2, username=username, codice_mostrato=codice)
        elif step == "2":
            username = request.form.get("username", "").strip()
            codice_inserito = request.form.get("codice", "").strip()
            recuperi = leggi_json(FILE_RECUPERO)
            recupero_valido = None
            for r in recuperi:
                if r["username"] == username and r["codice"] == codice_inserito and not r.get("usato", False):
                    recupero_valido = r
                    break
            if not recupero_valido:
                return render_template("recupero_password.html", errore="Codice non valido o scaduto", step=2, username=username)
            return render_template("recupero_password.html", step=3, username=username, codice=codice_inserito)
        elif step == "3":
            username = request.form.get("username", "").strip()
            nuova_password = request.form.get("nuova_password", "").strip()
            conferma_password = request.form.get("conferma_password", "").strip()
            if not nuova_password or len(nuova_password) < 4:
                return render_template("recupero_password.html", errore="Password minima 4 caratteri", step=3, username=username)
            if nuova_password != conferma_password:
                return render_template("recupero_password.html", errore="Le password non coincidono", step=3, username=username)
            utenti = leggi_json(FILE_UTENTI)
            for u in utenti:
                if u["username"] == username:
                    u["password"] = nuova_password
                    break
            scrivi_json(FILE_UTENTI, utenti)
            recuperi = leggi_json(FILE_RECUPERO)
            for r in recuperi:
                if r["username"] == username and not r.get("usato", False):
                    r["usato"] = True
                    break
            scrivi_json(FILE_RECUPERO, recuperi)
            return render_template("recupero_password.html", successo="✅ Password aggiornata! Ora puoi accedere.")
    return render_template("recupero_password.html", step=1)
# =====================================================
# =================== REGISTRAZIONE UTENTI ============
# =====================================================

@app.route("/registrazione", methods=["GET", "POST"])
def registrazione():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        conferma_password = request.form.get("conferma_password", "").strip()
        email = request.form.get("email", "").strip()
        nome_cognome = request.form.get("nome_cognome", "").strip()
        scuola = request.form.get("scuola", "").strip()
        captcha_risposta = request.form.get("captcha_risposta", "").strip()
        
        captcha_sessione = session.get("captcha", {})
        errori = []
        
        if not username or len(username) < 3:
            errori.append("Username minimo 3 caratteri")
        if not password or len(password) < 4:
            errori.append("Password minima 4 caratteri")
        if password != conferma_password:
            errori.append("Le password non coincidono")
        if not email or "@" not in email:
            errori.append("Email non valida")
        if not nome_cognome:
            errori.append("Nome e cognome obbligatori")
        if not scuola:
            errori.append("Scuola obbligatoria")
        
        try:
            if int(captcha_risposta) != captcha_sessione.get("risposta"):
                errori.append("CAPTCHA errato")
        except:
            errori.append("CAPTCHA errato")
        
        utenti = leggi_json(FILE_UTENTI)
        if any(u["username"] == username for u in utenti):
            errori.append("Username già esistente")
        
        if any(u.get("email") == email for u in utenti):
            errori.append("Email già registrata")
        
        if errori:
            session["captcha"] = genera_captcha()
            return render_template("registrazione.html", 
                                   errori=errori, 
                                   dati_inviati=request.form,
                                   captcha_domanda=session["captcha"]["domanda"])
        
        registrazioni = leggi_json(FILE_REGISTRAZIONI)
        nuova_registrazione = {
            "id": len(registrazioni) + 1,
            "username": username,
            "password": password,
            "email": email,
            "nome_cognome": nome_cognome,
            "scuola": scuola,
            "data_registrazione": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stato": "in_attesa",
            "admin_note": ""
        }
        registrazioni.append(nuova_registrazione)
        scrivi_json(FILE_REGISTRAZIONI, registrazioni)
        
        session["captcha"] = genera_captcha()
        
        return render_template("registrazione.html", 
                               successo="✅ Registrazione inviata! Attendi l'approvazione dell'admin.",
                               captcha_domanda=session["captcha"]["domanda"])
    
    session["captcha"] = genera_captcha()
    return render_template("registrazione.html", 
                           captcha_domanda=session["captcha"]["domanda"])

@app.route("/logout")
def logout():
    if "username" in session:
        sessioni = leggi_json(FILE_SESSIONI)
        sessioni = [s for s in sessioni if s["username"] != session["username"]]
        scrivi_json(FILE_SESSIONI, sessioni)
    session.clear()
    return redirect(url_for("home"))


# =====================================================
# =================== DASHBOARD USER ==================
# =====================================================

@app.route("/user")
def user_dashboard():
    if "username" not in session or session.get("role") != "user":
        return redirect(url_for("login"))
    aggiorna_attivita_sessione()
    avvisi = leggi_json(FILE_AVVISI)
    avvisi_attivi = [a for a in avvisi if a.get("attivo", True)]
    return render_template("server.html", username=session["username"], avvisi=avvisi_attivi)


# =====================================================
# =================== DASHBOARD ADMIN =================
# =====================================================

@app.route("/admin")
def admin_dashboard():
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login"))
    aggiorna_attivita_sessione()
    pulisci_sessioni_scadute()
    return render_template("admin.html", username=session["username"])


# =====================================================
# ======================== API ========================
# =====================================================

def login_required():
    return "username" in session

def admin_required():
    return "username" in session and session.get("role") == "admin"


# =====================================================
# ============= NOTIFICHE API =========================
# =====================================================

@app.route("/api/notifiche", methods=["GET"])
def api_notifiche():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    notifiche = leggi_json(FILE_NOTIFICHE)
    mie_notifiche = [n for n in notifiche if n.get("utente") == session["username"]]
    mie_notifiche.sort(key=lambda x: x.get("data", ""), reverse=True)
    return jsonify(mie_notifiche)

@app.route("/api/notifiche/<int:id>", methods=["PUT"])
def api_notifica_letta(id):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    notifiche = leggi_json(FILE_NOTIFICHE)
    indice = next((i for i, n in enumerate(notifiche) if n["id"] == id), None)
    if indice is None:
        return jsonify({"error": "Notifica non trovata"}), 404
    if notifiche[indice].get("utente") != session["username"]:
        return jsonify({"error": "Non autorizzato"}), 403
    notifiche[indice]["letta"] = True
    notifiche[indice]["data_lettura"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scrivi_json(FILE_NOTIFICHE, notifiche)
    return jsonify({"success": True})

@app.route("/api/notifiche/segna-tutte-lette", methods=["POST"])
def api_notifiche_tutte_lette():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    notifiche = leggi_json(FILE_NOTIFICHE)
    for n in notifiche:
        if n.get("utente") == session["username"] and not n.get("letta", False):
            n["letta"] = True
            n["data_lettura"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scrivi_json(FILE_NOTIFICHE, notifiche)
    return jsonify({"success": True})


# =====================================================
# ============= TICKET API ============================
# =====================================================

@app.route("/api/ticket", methods=["GET", "POST"])
def api_ticket():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    ticket_list = leggi_json(FILE_TICKET)
    if request.method == "GET":
        if session["role"] == "admin":
            return jsonify(ticket_list)
        else:
            miei_ticket = [t for t in ticket_list if t.get("utente") == session["username"]]
            return jsonify(miei_ticket)
    elif request.method == "POST":
        if session["role"] == "admin":
            return jsonify({"error": "Gli admin non possono creare ticket"}), 403
        data = request.get_json()
        nuovo_ticket = {
            "id": len(ticket_list) + 1,
            "utente": session["username"],
            "oggetto": data.get("oggetto", ""),
            "messaggio": data.get("messaggio", ""),
            "priorita": data.get("priorita", "media"),
            "stato": "aperto",
            "data_apertura": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_chiusura": None,
            "admin_assegnato": None,
            "risposte": []
        }
        ticket_list.append(nuovo_ticket)
        scrivi_json(FILE_TICKET, ticket_list)
        utenti = leggi_json(FILE_UTENTI)
        admin_list = [u["username"] for u in utenti if u.get("role") == "admin"]
        for admin_username in admin_list:
            crea_notifica(username=admin_username, tipo="ticket", titolo=f"🎫 Nuovo Ticket #{nuovo_ticket['id']}", messaggio=f"{session['username']} ha creato un nuovo ticket: {nuovo_ticket['oggetto']}", link="/admin#ticket")
        invia_email_ticket(nuovo_ticket)
        return jsonify({"success": True, "message": "Ticket creato", "ticket_id": nuovo_ticket["id"]})

@app.route("/api/ticket/<int:id>", methods=["GET", "PUT", "DELETE"])
def api_ticket_dettaglio(id):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    ticket_list = leggi_json(FILE_TICKET)
    ticket = next((t for t in ticket_list if t["id"] == id), None)
    if not ticket:
        return jsonify({"error": "Ticket non trovato"}), 404
    is_admin = session["role"] == "admin"
    is_creatore = ticket.get("utente") == session["username"]
    if not is_admin and not is_creatore:
        return jsonify({"error": "Non autorizzato"}), 403
    if request.method == "GET":
        return jsonify(ticket)
    elif request.method == "PUT":
        data = request.get_json()
        if is_admin:
            if "stato" in data and data["stato"] in ["aperto", "in_lavorazione", "risolto", "chiuso"]:
                ticket["stato"] = data["stato"]
                if data["stato"] in ["risolto", "chiuso"]:
                    ticket["data_chiusura"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if "risposta" in data and data["risposta"]:
                risposta = {"da": "admin", "admin": session["username"], "messaggio": data["risposta"], "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                ticket["risposte"].append(risposta)
                crea_notifica(username=ticket["utente"], tipo="ticket", titolo="💬 Risposta al tuo ticket", messaggio=f"L'admin {session['username']} ha risposto al ticket #{id}", link="/user#ticket")
        elif is_creatore and ticket["stato"] == "aperto":
            if "messaggio" in data and data["messaggio"]:
                risposta = {"da": "utente", "utente": session["username"], "messaggio": data["messaggio"], "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                ticket["risposte"].append(risposta)
        for i, t in enumerate(ticket_list):
            if t["id"] == id:
                ticket_list[i] = ticket
                break
        scrivi_json(FILE_TICKET, ticket_list)
        return jsonify({"success": True, "message": "Ticket aggiornato"})
    elif request.method == "DELETE":
        if is_admin or (is_creatore and len(ticket.get("risposte", [])) == 0):
            ticket_list = [t for t in ticket_list if t["id"] != id]
            scrivi_json(FILE_TICKET, ticket_list)
            return jsonify({"success": True, "message": "Ticket eliminato"})
        else:
            return jsonify({"error": "Non puoi eliminare ticket con risposte"}), 403


# =====================================================
# ============= REGISTRAZIONI =========================
# =====================================================

@app.route("/api/registrazioni", methods=["GET"])
def api_registrazioni_lista():
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    return jsonify(leggi_json(FILE_REGISTRAZIONI))

@app.route("/api/registrazioni/<int:id>", methods=["PUT", "DELETE"])
def api_registrazioni_gestisci(id):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    registrazioni = leggi_json(FILE_REGISTRAZIONI)
    indice = next((i for i, r in enumerate(registrazioni) if r["id"] == id), None)
    if indice is None:
        return jsonify({"error": "Registrazione non trovata"}), 404
    if request.method == "DELETE":
        registrazioni.pop(indice)
        scrivi_json(FILE_REGISTRAZIONI, registrazioni)
        return jsonify({"success": True, "message": "Registrazione eliminata"})
    if request.method == "PUT":
        data = request.get_json()
        if "stato" in data and data["stato"] in ["approvato", "rifiutato"]:
            registrazioni[indice]["stato"] = data["stato"]
            registrazioni[indice]["admin_note"] = data.get("admin_note", "")
            registrazioni[indice]["data_approvazione"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scrivi_json(FILE_REGISTRAZIONI, registrazioni)
            if data["stato"] == "approvato":
                reg = registrazioni[indice]
                utenti = leggi_json(FILE_UTENTI)
                nuovo_utente = {
                    "username": reg["username"],
                    "password": reg["password"],
                    "email": reg["email"],
                    "nome_cognome": reg["nome_cognome"],
                    "scuola": reg["scuola"],
                    "role": "user",
                    "stato": "attivo",
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "telefono": "",
                    "data_nascita": "",
                    "indirizzo": "",
                    "citta": "",
                    "cap": "",
                    "admin_note": "",
                    "account_status": "attivo"
                }
                utenti.append(nuovo_utente)
                scrivi_json(FILE_UTENTI, utenti)
                crea_notifica(username=reg["username"], tipo="registrazione", titolo="✅ Registrazione approvata", messaggio="Il tuo account è stato approvato! Ora puoi accedere.", link="/login")
            return jsonify({"success": True, "message": f"Registrazione {data['stato']}"})
        return jsonify({"error": "Stato non valido"}), 400
# DOPO aver salvato la registrazione, aggiungi questo:

# Se siamo su Render con SQLite, approva automaticamente la registrazione
if os.getenv("USE_SQLITE") == "true":
    # Crea direttamente l'utente nella tabella users
    nuovo_utente = User(
        username=username,
        password=password,
        email=email,
        nome_cognome=nome_cognome,
        scuola=scuola,
        role="user",
        stato="attivo",
        account_status="attivo"
    )
    db.session.add(nuovo_utente)
    db.session.commit()
    
    return render_template("registrazione.html", 
                          successo="✅ Registrazione completata! Ora puoi accedere.",
                          captcha_domanda=session["captcha"]["domanda"])
else:
    # Comportamento normale: salva in attesa di approvazione
    registrazioni = leggi_json(FILE_REGISTRAZIONI)
    # ... codice esistente ...

@app.route("/api/registrazioni/<int:id>/modifica", methods=["PUT"])
def api_registrazioni_modifica(id):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    registrazioni = leggi_json(FILE_REGISTRAZIONI)
    indice = next((i for i, r in enumerate(registrazioni) if r["id"] == id), None)
    if indice is None:
        return jsonify({"error": "Registrazione non trovata"}), 404
    data = request.get_json()
    if "username" in data:
        utenti = leggi_json(FILE_UTENTI)
        if any(u["username"] == data["username"] for u in utenti):
            return jsonify({"error": "Username già esistente"}), 400
        registrazioni[indice]["username"] = data["username"]
    if "email" in data:
        registrazioni[indice]["email"] = data["email"]
    if "nome_cognome" in data:
        registrazioni[indice]["nome_cognome"] = data["nome_cognome"]
    if "scuola" in data:
        registrazioni[indice]["scuola"] = data["scuola"]
    if "password" in data and data["password"]:
        registrazioni[indice]["password"] = data["password"]
    scrivi_json(FILE_REGISTRAZIONI, registrazioni)
    return jsonify({"success": True, "message": "Dati aggiornati"})


# =====================================================
# ============= UTENTI ANAGRAFICA =====================
# =====================================================

@app.route("/api/utenti-anagrafica/<int:index>", methods=["GET", "PUT"])
def api_utenti_anagrafica(index):
    """
    GET: Ottieni scheda anagrafica completa di un utente
    PUT: Modifica scheda anagrafica (solo admin)
    """
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    
    utenti = leggi_json(FILE_UTENTI)
    if index >= len(utenti):
        return jsonify({"error": "Utente non trovato"}), 404
    
    utente = utenti[index]
    
    if request.method == "GET":
        # Calcola statistiche
        voti_list = leggi_json(FILE_VOTI)
        recensioni_list = leggi_json(FILE_RECENSIONI)
        sessioni_list = leggi_json(FILE_SESSIONI)
        
        anagrafica = {
            "id": index,
            "username": utente.get("username", ""),
            "email": utente.get("email", ""),
            "nome_cognome": utente.get("nome_cognome", ""),
            "scuola": utente.get("scuola", ""),
            "telefono": utente.get("telefono", ""),
            "data_nascita": utente.get("data_nascita", ""),
            "indirizzo": utente.get("indirizzo", ""),
            "citta": utente.get("citta", ""),
            "cap": utente.get("cap", ""),
            "role": utente.get("role", "user"),
            "stato": utente.get("stato", "attivo"),
            "account_status": utente.get("account_status", "attivo"),
            "admin_note": utente.get("admin_note", ""),
            "created_at": utente.get("created_at", "N/A"),
            "last_login": "N/A",
            "voti_count": len([v for v in voti_list if v.get("user") == utente["username"]]),
            "recensioni_count": len([r for r in recensioni_list if r.get("user") == utente["username"]]),
            "sessioni_attive": len([s for s in sessioni_list if s["username"] == utente["username"]])
        }
        
        # Trova ultimo login
        sessioni_utente = [s for s in sessioni_list if s["username"] == utente["username"]]
        if sessioni_utente:
            anagrafica["last_login"] = max(s["login_time"] for s in sessioni_utente)
        
        return jsonify(anagrafica)
    
    elif request.method == "PUT":
        if not admin_required():
            return jsonify({"error": "Solo admin possono modificare"}), 403
        
        if utenti[index]["username"] == session["username"]:
            return jsonify({"error": "Non puoi modificare il tuo stesso account"}), 403
        
        data = request.get_json()
        
        # Campi modificabili
        campi_modificabili = ["email", "nome_cognome", "scuola", "telefono", "data_nascita", 
                             "indirizzo", "citta", "cap", "account_status", "admin_note", "role"]
        
        for campo in campi_modificabili:
            if campo in data:
                utenti[index][campo] = data[campo]
        
        # Se cambia password
        if "password" in data and data["password"]:
            utenti[index]["password"] = data["password"]
        
        scrivi_json(FILE_UTENTI, utenti)
        
        # Notifica all'utente se ci sono modifiche importanti
        if "account_status" in data or "role" in data:
            status_msg = ""
            if data.get("account_status") == "sospeso":
                status_msg = "Il tuo account è stato sospeso. Contatta l'admin."
            elif data.get("account_status") == "bannato":
                status_msg = "Il tuo account è stato bannato."
            elif data.get("account_status") == "attivo":
                status_msg = "Il tuo account è stato riattivato."
            
            if status_msg:
                crea_notifica(
                    username=utenti[index]["username"],
                    tipo="sistema",
                    titolo="⚙️ Stato account aggiornato",
                    messaggio=status_msg,
                    link="/user" if data.get("account_status") == "attivo" else "/login"
                )
        
        return jsonify({"success": True, "message": "Scheda anagrafica aggiornata"})

# =====================================================
# ============= SESSIONI ATTIVE =======================
# =====================================================

@app.route("/api/sessioni", methods=["GET"])
def api_sessioni_lista():
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    return jsonify(leggi_json(FILE_SESSIONI))

@app.route("/api/sessioni/<session_id>", methods=["DELETE"])
def api_sessioni_termina(session_id):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    sessioni = leggi_json(FILE_SESSIONI)
    sessione_trovata = next((s for s in sessioni if s["session_id"] == session_id), None)
    if not sessione_trovata:
        return jsonify({"error": "Sessione non trovata"}), 404
    if sessione_trovata["username"] == session["username"]:
        return jsonify({"error": "Non puoi disconnettere te stesso"}), 403
    sessioni = [s for s in sessioni if s["session_id"] != session_id]
    scrivi_json(FILE_SESSIONI, sessioni)
    return jsonify({"success": True, "message": f"Sessione di {sessione_trovata['username']} terminata"})


# =====================================================
# ========== SEGNALAZIONI UTENTI ======================
# =====================================================

@app.route("/api/segnalazioni", methods=["GET", "POST"])
def api_segnalazioni():
    if request.method == "GET":
        if not admin_required():
            return jsonify({"error": "Non autorizzato. Solo admin."}), 403
        return jsonify(leggi_json(FILE_SEGNALAZIONI))
    elif request.method == "POST":
        if not login_required():
            return jsonify({"error": "Non autorizzato"}), 403
        data = request.get_json()
        segnalazioni_esistenti = leggi_json(FILE_SEGNALAZIONI)
        nuova_segnalazione = {
            "id": len(segnalazioni_esistenti) + 1,
            "tipo": data.get("tipo", "recensione"),
            "indice": data.get("indice"),
            "motivo": data.get("motivo", ""),
            "segnalatore": session["username"],
            "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stato": "pending"
        }
        segnalazioni_esistenti.append(nuova_segnalazione)
        scrivi_json(FILE_SEGNALAZIONI, segnalazioni_esistenti)
        utenti = leggi_json(FILE_UTENTI)
        admin_list = [u["username"] for u in utenti if u.get("role") == "admin"]
        for admin_username in admin_list:
            crea_notifica(username=admin_username, tipo="segnalazione", titolo="🚩 Nuova Segnalazione", messaggio=f"{session['username']} ha segnalato un contenuto", link="/admin#segnalazioni")
        return jsonify({"success": True, "message": "Segnalazione inviata"})

@app.route("/api/segnalazioni/<int:id>", methods=["PUT", "DELETE"])
def api_segnalazioni_gestisci(id):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    segnalazioni = leggi_json(FILE_SEGNALAZIONI)
    indice = next((i for i, s in enumerate(segnalazioni) if s["id"] == id), None)
    if indice is None:
        return jsonify({"error": "Segnalazione non trovata"}), 404
    if request.method == "DELETE":
        segnalazioni.pop(indice)
        scrivi_json(FILE_SEGNALAZIONI, segnalazioni)
        return jsonify({"success": True, "message": "Segnalazione eliminata"})
    if request.method == "PUT":
        data = request.get_json()
        if "stato" in data and data["stato"] in ["pending", "resolved", "dismissed"]:
            segnalazioni[indice]["stato"] = data["stato"]
            segnalazioni[indice]["admin_note"] = data.get("admin_note", "")
            segnalazioni[indice]["data_chiusura"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            scrivi_json(FILE_SEGNALAZIONI, segnalazioni)
            return jsonify({"success": True, "message": f"Segnalazione {data['stato']}"})
        return jsonify({"error": "Stato non valido"}), 400


# =====================================================
# =================== GESTIONE UTENTI =================
# =====================================================

@app.route("/api/utenti", methods=["GET"])
def api_utenti_lista():
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    utenti = leggi_json(FILE_UTENTI)
    voti_list = leggi_json(FILE_VOTI)
    recensioni_list = leggi_json(FILE_RECENSIONI)
    dati_utenti = []
    for u in utenti:
        dati_utenti.append({
            "username": u["username"],
            "role": u.get("role", "user"),
            "created_at": u.get("created_at", "N/A"),
            "voti_count": len([v for v in voti_list if v.get("user") == u["username"]]),
            "recensioni_count": len([r for r in recensioni_list if r.get("user") == u["username"]])
        })
    return jsonify(dati_utenti)

@app.route("/api/utenti/<int:index>", methods=["PUT", "DELETE"])
def api_utenti_mod(index):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    utenti = leggi_json(FILE_UTENTI)
    if index >= len(utenti):
        return jsonify({"error": "Utente non trovato"}), 404
    if utenti[index]["username"] == session["username"]:
        return jsonify({"error": "Non puoi modificare il tuo stesso account"}), 403
    if request.method == "DELETE":
        username_eliminato = utenti[index]["username"]
        utenti.pop(index)
        scrivi_json(FILE_UTENTI, utenti)
        return jsonify({"success": True, "message": f"Utente {username_eliminato} eliminato"})
    if request.method == "PUT":
        data = request.get_json()
        if "role" in data:
            utenti[index]["role"] = data["role"]
            scrivi_json(FILE_UTENTI, utenti)
            return jsonify({"success": True, "message": f"Ruolo aggiornato a {data['role']}"})
        return jsonify({"error": "Dati non validi"}), 400

@app.route("/api/utenti/crea", methods=["POST"])
def api_utenti_crea():
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    data = request.get_json()
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "user")
    if not username or not password:
        return jsonify({"error": "Username e password richiesti"}), 400
    if role not in ["user", "admin"]:
        return jsonify({"error": "Ruolo non valido. Usa 'user' o 'admin'"}), 400
    utenti = leggi_json(FILE_UTENTI)
    if any(u["username"] == username for u in utenti):
        return jsonify({"error": "Username già esistente"}), 400
    nuovo_utente = {
        "username": username,
        "password": password,
        "role": role,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "telefono": "",
        "data_nascita": "",
        "indirizzo": "",
        "citta": "",
        "cap": "",
        "admin_note": "",
        "account_status": "attivo"
    }
    utenti.append(nuovo_utente)
    scrivi_json(FILE_UTENTI, utenti)
    return jsonify({"success": True, "message": f"Utente {username} creato con ruolo {role}"})

@app.route("/api/utenti/<int:index>/credenziali", methods=["PUT"])
def api_utenti_modifica_credenziali(index):
    if not admin_required():
        return jsonify({"error": "Non autorizzato. Solo admin."}), 403
    utenti = leggi_json(FILE_UTENTI)
    if index >= len(utenti):
        return jsonify({"error": "Utente non trovato"}), 404
    if utenti[index]["username"] == session["username"]:
        return jsonify({"error": "Non puoi modificare il tuo stesso account"}), 403
    data = request.get_json()
    nuovo_username = data.get("username", "").strip()
    nuova_password = data.get("password", "").strip()
    if nuovo_username and nuovo_username != utenti[index]["username"]:
        if any(u["username"] == nuovo_username for u in utenti):
            return jsonify({"error": "Username già esistente"}), 400
        utenti[index]["username"] = nuovo_username
    if nuova_password:
        utenti[index]["password"] = nuova_password
    scrivi_json(FILE_UTENTI, utenti)
    return jsonify({"success": True, "message": "Credenziali aggiornate", "username": utenti[index]["username"]})


# =====================================================
# ============= MODIFICA PROFILO UTENTE ===============
# =====================================================

@app.route("/api/profilo", methods=["GET", "PUT"])
def api_profilo():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    if request.method == "GET":
        utenti = leggi_json(FILE_UTENTI)
        for u in utenti:
            if u["username"] == session["username"]:
                return jsonify({
                    "username": u["username"],
                    "email": u.get("email", ""),
                    "nome_cognome": u.get("nome_cognome", ""),
                    "scuola": u.get("scuola", ""),
                    "role": u.get("role", "user"),
                    "created_at": u.get("created_at", "N/A")
                })
        return jsonify({"error": "Utente non trovato"}), 404
    elif request.method == "PUT":
        data = request.get_json()
        utenti = leggi_json(FILE_UTENTI)
        indice = next((i for i, u in enumerate(utenti) if u["username"] == session["username"]), None)
        if indice is None:
            return jsonify({"error": "Utente non trovato"}), 404
        if "email" in data and data["email"]:
            if "@" not in data["email"]:
                return jsonify({"error": "Email non valida"}), 400
            utenti[indice]["email"] = data["email"]
        if "nome_cognome" in data and data["nome_cognome"]:
            utenti[indice]["nome_cognome"] = data["nome_cognome"]
        if "scuola" in data and data["scuola"]:
            utenti[indice]["scuola"] = data["scuola"]
        if "password" in data and data["password"]:
            if len(data["password"]) < 4:
                return jsonify({"error": "Password minima 4 caratteri"}), 400
            utenti[indice]["password"] = data["password"]
        scrivi_json(FILE_UTENTI, utenti)
        return jsonify({"success": True, "message": "Profilo aggiornato"})


# =====================================================
# ============= STORICO VOTI ==========================
# =====================================================

@app.route("/api/storico-voti", methods=["GET"])
def api_storico_voti():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    voti = leggi_json(FILE_VOTI)
    miei_voti = [v for v in voti if v.get("user") == session["username"]]
    for i, v in enumerate(miei_voti):
        v["index"] = i
    return jsonify(miei_voti)


# =====================================================
# ======================== VOTI =======================
# =====================================================

@app.route("/api/voti", methods=["GET", "POST"])
def api_voti():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    voti = leggi_json(FILE_VOTI)
    if request.method == "POST":
        nuovo = request.json
        nuovo["user"] = session["username"]
        nuovo["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        voti.append(nuovo)
        scrivi_json(FILE_VOTI, voti)
        return jsonify({"success": True})
    return jsonify(voti)

@app.route("/api/voti/<int:index>", methods=["PUT", "DELETE"])
def api_voti_mod(index):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    voti = leggi_json(FILE_VOTI)
    if index >= len(voti):
        return jsonify({"error": "Indice non valido"}), 400
    if session["role"] != "admin" and voti[index]["user"] != session["username"]:
        return jsonify({"error": "Non autorizzato. Puoi modificare solo i tuoi voti."}), 403
    if request.method == "DELETE":
        voti.pop(index)
        scrivi_json(FILE_VOTI, voti)
        return jsonify({"success": True})
    if request.method == "PUT":
        dati_modifica = request.json
        voti[index]["voto"] = dati_modifica.get("voto", voti[index]["voto"])
        voti[index]["nomeProf"] = dati_modifica.get("nomeProf", voti[index]["nomeProf"])
        voti[index]["materia"] = dati_modifica.get("materia", voti[index]["materia"])
        voti[index]["scuola"] = dati_modifica.get("scuola", voti[index]["scuola"])
        scrivi_json(FILE_VOTI, voti)
        return jsonify({"success": True})


# =====================================================
# ==================== RECENSIONI =====================
# =====================================================

@app.route("/api/recensioni", methods=["GET", "POST"])
def api_recensioni():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    recensioni = leggi_json(FILE_RECENSIONI)
    if request.method == "POST":
        nuovo = request.json
        nuovo["user"] = session["username"]
        nuovo["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        nuovo["likes"] = 0
        nuovo["dislikes"] = 0
        nuovo["user_likes"] = []
        nuovo["user_dislikes"] = []
        nuovo["commenti"] = []
        recensioni.append(nuovo)
        scrivi_json(FILE_RECENSIONI, recensioni)
        return jsonify({"success": True})
    return jsonify(recensioni)

@app.route("/api/recensioni/<int:index>", methods=["PUT", "DELETE"])
def api_recensioni_mod(index):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    recensioni = leggi_json(FILE_RECENSIONI)
    if index >= len(recensioni):
        return jsonify({"error": "Indice non valido"}), 400
    if session["role"] != "admin" and recensioni[index]["user"] != session["username"]:
        return jsonify({"error": "Non autorizzato. Puoi modificare solo le tue recensioni."}), 403
    if request.method == "DELETE":
        recensioni.pop(index)
        scrivi_json(FILE_RECENSIONI, recensioni)
        return jsonify({"success": True})
    if request.method == "PUT":
        dati_modifica = request.json
        recensioni[index]["recensione"] = dati_modifica.get("recensione", recensioni[index]["recensione"])
        recensioni[index]["nomeProfRec"] = dati_modifica.get("nomeProfRec", recensioni[index]["nomeProfRec"])
        recensioni[index]["scuola"] = dati_modifica.get("scuola", recensioni[index].get("scuola"))
        scrivi_json(FILE_RECENSIONI, recensioni)
        return jsonify({"success": True})

@app.route("/api/recensioni/<int:id>/like", methods=["POST"])
def api_recensioni_like(id):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    recensioni = leggi_json(FILE_RECENSIONI)
    if id >= len(recensioni):
        return jsonify({"error": "Recensione non trovata"}), 404
    data = request.get_json()
    azione = data.get("azione")
    username = session["username"]
    if "likes" not in recensioni[id]:
        recensioni[id]["likes"] = 0
    if "dislikes" not in recensioni[id]:
        recensioni[id]["dislikes"] = 0
    if "user_likes" not in recensioni[id]:
        recensioni[id]["user_likes"] = []
    if "user_dislikes" not in recensioni[id]:
        recensioni[id]["user_dislikes"] = []
    if username in recensioni[id].get("user_likes", []):
        recensioni[id]["user_likes"].remove(username)
        recensioni[id]["likes"] = max(0, recensioni[id]["likes"] - 1)
    if username in recensioni[id].get("user_dislikes", []):
        recensioni[id]["user_dislikes"].remove(username)
        recensioni[id]["dislikes"] = max(0, recensioni[id]["dislikes"] - 1)
    if azione == "like":
        if username not in recensioni[id]["user_likes"]:
            recensioni[id]["user_likes"].append(username)
            recensioni[id]["likes"] = recensioni[id]["likes"] + 1
    elif azione == "dislike":
        if username not in recensioni[id]["user_dislikes"]:
            recensioni[id]["user_dislikes"].append(username)
            recensioni[id]["dislikes"] = recensioni[id]["dislikes"] + 1
    scrivi_json(FILE_RECENSIONI, recensioni)
    return jsonify({"success": True, "likes": recensioni[id]["likes"], "dislikes": recensioni[id]["dislikes"]})

@app.route("/api/recensioni/<int:rec_id>/commenti", methods=["GET", "POST"])
def api_recensioni_commenti(rec_id):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    recensioni = leggi_json(FILE_RECENSIONI)
    if rec_id >= len(recensioni):
        return jsonify({"error": "Recensione non trovata"}), 404
    if request.method == "GET":
        commenti = recensioni[rec_id].get("commenti", [])
        return jsonify(commenti)
    elif request.method == "POST":
        data = request.get_json()
        testo = data.get("testo", "").strip()
        if not testo:
            return jsonify({"error": "Commento vuoto"}), 400
        if "commenti" not in recensioni[rec_id]:
            recensioni[rec_id]["commenti"] = []
        nuovo_commento = {"id": len(recensioni[rec_id]["commenti"]) + 1, "utente": session["username"], "ruolo": session.get("role", "user"), "testo": testo, "data": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "likes": 0, "dislikes": 0, "user_likes": [], "user_dislikes": []}
        recensioni[rec_id]["commenti"].append(nuovo_commento)
        scrivi_json(FILE_RECENSIONI, recensioni)
        return jsonify({"success": True, "message": "Commento aggiunto"})

@app.route("/api/recensioni/<int:rec_id>/commenti/<int:comm_id>/like", methods=["POST"])
def api_recensioni_commenti_like(rec_id, comm_id):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    recensioni = leggi_json(FILE_RECENSIONI)
    if rec_id >= len(recensioni):
        return jsonify({"error": "Recensione non trovata"}), 404
    if "commenti" not in recensioni[rec_id] or comm_id >= len(recensioni[rec_id]["commenti"]):
        return jsonify({"error": "Commento non trovato"}), 404
    commento = recensioni[rec_id]["commenti"][comm_id]
    data = request.get_json()
    azione = data.get("azione")
    username = session["username"]
    if "likes" not in commento:
        commento["likes"] = 0
    if "dislikes" not in commento:
        commento["dislikes"] = 0
    if "user_likes" not in commento:
        commento["user_likes"] = []
    if "user_dislikes" not in commento:
        commento["user_dislikes"] = []
    if username in commento.get("user_likes", []):
        commento["user_likes"].remove(username)
        commento["likes"] = max(0, commento["likes"] - 1)
    if username in commento.get("user_dislikes", []):
        commento["user_dislikes"].remove(username)
        commento["dislikes"] = max(0, commento["dislikes"] - 1)
    if azione == "like":
        if username not in commento["user_likes"]:
            commento["user_likes"].append(username)
            commento["likes"] = commento["likes"] + 1
    elif azione == "dislike":
        if username not in commento["user_dislikes"]:
            commento["user_dislikes"].append(username)
            commento["dislikes"] = commento["dislikes"] + 1
    scrivi_json(FILE_RECENSIONI, recensioni)
    return jsonify({"success": True, "likes": commento["likes"], "dislikes": commento["dislikes"]})


# =====================================================
# ==================== PROFESSORI =====================
# =====================================================

@app.route("/api/professori", methods=["GET", "POST"])
def api_professori():
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    professori = leggi_json(FILE_PROFESSORI)
    if request.method == "POST":
        nuovo = request.json
        professori.append(nuovo)
        scrivi_json(FILE_PROFESSORI, professori)
        return jsonify({"success": True})
    return jsonify(professori)

@app.route('/api/professori/<int:index>', methods=['PUT','DELETE'])
def api_professori_mod(index):
    if not login_required():
        return jsonify({"error": "Non autorizzato"}), 403
    professori = leggi_json(FILE_PROFESSORI)
    if index >= len(professori):
        return jsonify({"error": "Indice non valido"}), 400
    if request.method == "DELETE":
        professori.pop(index)
        scrivi_json(FILE_PROFESSORI, professori)
        return jsonify({"success": True})
    if request.method == "PUT":
        professori[index].update(request.json)
        scrivi_json(FILE_PROFESSORI, professori)
        return jsonify({"success": True})

# ═══════════════════════════════════════════════════════════
# ROUTE DEBUG: CREA UTENTI DI TEST (accessibile solo da admin)
# ═══════════════════════════════════════════════════════════
@app.route("/debug-crea-utenti")
def debug_crea_utenti():
    """Crea utenti di test nel database - SOLO PER DEBUG"""
    
    # 🔧 TEMPORANEO: Commenta questa riga per creare utenti senza login
    # if not admin_required():
    #     return "❌ Accesso negato. Solo admin.", 403
    
    try:
        with app.app_context():
            # Crea admin di test se non esiste
            if not User.query.filter_by(username="admin").first():
                admin = User(
                    username="admin",
                    password="admin123",
                    email="admin@test.com",
                    nome_cognome="Admin Test",
                    scuola="Test School",
                    role="admin",
                    stato="attivo",
                    account_status="attivo"
                )
                db.session.add(admin)
                db.session.commit()
                msg_admin = "✅ Admin creato: admin / admin123<br>"
            else:
                msg_admin = "⚠️ Admin già esiste<br>"
            
            # Crea utente normale di test se non esiste
            if not User.query.filter_by(username="testuser").first():
                user = User(
                    username="testuser",
                    password="test123",
                    email="test@test.com",
                    nome_cognome="Test User",
                    scuola="Test School",
                    role="user",
                    stato="attivo",
                    account_status="attivo"
                )
                db.session.add(user)
                db.session.commit()
                msg_user = "✅ Utente creato: testuser / test123<br>"
            else:
                msg_user = "⚠️ Utente test già esiste<br>"
            
            return f"""
            <h2>🔧 Debug: Utenti di Test</h2>
            <p>{msg_admin}{msg_user}</p>
            <hr>
            <p><strong>Credenziali:</strong></p>
            <ul>
                <li>👑 Admin: <code>admin</code> / <code>admin123</code></li>
                <li>👤 Utente: <code>testuser</code> / <code>test123</code></li>
            </ul>
            <p><a href="/login">🔐 Vai al Login</a> | <a href="/admin">⚙️ Vai alla Dashboard Admin</a></p>
            <p style="color:#f44336;font-weight:bold;">⚠️ ROUTE PUBBLICA - Rimuovi il bypass dopo il test!</p>
            """
    except Exception as e:
        return f"❌ Errore: {e}", 500
        # ═══════════════════════════════════════════════════════════
# ROUTE TEST MINIMALISTA (per debug)
# ═══════════════════════════════════════════════════════════
@app.route("/test")
def test_route():
    return "✅ ROUTE TEST FUNZIONA! Se vedi questo, il routing è OK."
# =====================================================
# ===================== AVVIO =========================
# =====================================================

if __name__ == "__main__":
    if not os.path.exists(FILE_SESSIONI):
        scrivi_json(FILE_SESSIONI, [])
    if not os.path.exists(FILE_SEGNALAZIONI):
        scrivi_json(FILE_SEGNALAZIONI, [])
    if not os.path.exists(FILE_REGISTRAZIONI):
        scrivi_json(FILE_REGISTRAZIONI, [])
    if not os.path.exists(FILE_AVVISI):
        scrivi_json(FILE_AVVISI, [])
    if not os.path.exists(FILE_TICKET):
        scrivi_json(FILE_TICKET, [])
    if not os.path.exists(FILE_NOTIFICHE):
        scrivi_json(FILE_NOTIFICHE, [])
    if not os.path.exists(FILE_RECUPERO):
        scrivi_json(FILE_RECUPERO, [])
if __name__ == "__main__":
    # Crea le tabelle se non esistono
    with app.app_context():
        db.create_all()
        print("✅ Tabelle database create/verificate!")
    
    # Per sviluppo locale
    app.run(debug=True, host="0.0.0.0", port=5000)
