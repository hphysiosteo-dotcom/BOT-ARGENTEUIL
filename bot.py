"""
BOT SECRETAIRE — CABINET DE KINESITHERAPIE DU VAL D'ARGENTEUIL
Repond automatiquement aux patients : appels, SMS, WhatsApp
"""

import os, json
from datetime import datetime
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from twilio.twiml.voice_response import VoiceResponse
import anthropic

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
ALERT_NUMBER = os.environ.get("ALERT_NUMBER", "whatsapp:+33XXXXXXXXX")

# WhatsApp de chaque kine
KINE_WHATSAPP = {
    "Kaouthar Beddiaf": os.environ.get("WA_KAOUTHAR", "whatsapp:+33666679070"),
    "Yann Chatenay": os.environ.get("WA_YANN", "whatsapp:+33633735234"),
    "Lucas Gousseff": os.environ.get("WA_LUCAS", "whatsapp:+33659014769"),
    "Samy Hajji": os.environ.get("WA_SAMY", "whatsapp:+33670095899"),
    "Ahmed Jaballah": os.environ.get("WA_AHMED", "whatsapp:+33651693344"),
    "Mehdi Moulay Ben Mohand": os.environ.get("WA_MEHDI", "whatsapp:+32471901673"),
    "Mohammed-Houcine Saidi-Remili": os.environ.get("WA_HOUCINE", "whatsapp:+33XXXXXXXXX"),
}

# Amine recoit le meme resume que Houcine (shadow, pas visible dans les messages)
WA_AMINE_SHADOW = os.environ.get("WA_AMINE", "whatsapp:+33785987772")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ============================================================
# BASE DE CONNAISSANCES
# ============================================================

CONTEXTE_CABINET = """
Tu es le secretaire du Cabinet de Kinesitherapie du Val d'Argenteuil.

NOM : Cabinet de Kinesitherapie du Val d'Argenteuil
ADRESSE : 11 place d'Alembert, Argenteuil
TELEPHONE : 07 83 73 43 24
HORAIRES : Ouvert du lundi au dimanche

COMMENT VENIR :
- Le cabinet est situe SUR LA PLACE D'ALEMBERT, et non au pied de l'immeuble
- Se garer a proximite
- Il existe un parking souterrain
- Prendre les escaliers qui menent a la place
- En face d'une geante fresque avec la Tour Eiffel

EQUIPE : 7 kinesitherapeutes
TARIFS : Conventionne secteur 1, sans depassement d'honoraires
PRISE DE RDV : Uniquement via Doctolib

LIENS DOCTOLIB DE CHAQUE KINE :
- Kaouthar Beddiaf → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/kaouthar-beddiaf
- Yann Chatenay → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/yann-chatenay
- Lucas Gousseff → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/lucas-goussef-suresnes
- Samy Hajji → https://www.doctolib.fr/masseur-kinesitherapeute/montreuil/samy-hajji
- Ahmed Jaballah → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/ahmed-jaballah
- Mehdi Moulay Ben Mohand → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/mehdi-moulay-ben-mohand
- Mohammed-Houcine Saidi-Remili → https://www.doctolib.fr/masseur-kinesitherapeute/argenteuil/houcine-saidi-remili

COMMENT ORIENTER VERS DOCTOLIB :
- Si le patient ne demande pas de kine en particulier : demander avec qui il veut prendre RDV.
- Si le patient demande un kine par son nom : donner le lien Doctolib direct de ce kine.
- Ne jamais donner tous les liens d'un coup. Donner uniquement le lien pertinent.

RECONNAISSANCE DES NOMS — TRES IMPORTANT :
Les patients vont souvent ecorcher les noms, ecrire juste le prenom ou juste le nom,
ou faire des fautes. Tu dois DEVINER et SUGGERER. Exemples :

Prenom seul :
- "Kaouthar" ou "Kaoutar" ou "Kawtar" → Kaouthar Beddiaf
- "Yann" ou "Yan" → Yann Chatenay
- "Lucas" → Lucas Gousseff
- "Samy" ou "Sami" ou "Sammy" → Samy Hajji
- "Ahmed" ou "Ahmad" → Ahmed Jaballah
- "Mehdi" ou "Mehdy" → Mehdi Moulay Ben Mohand
- "Houcine" ou "Houssine" ou "Hussein" ou "Mohammed" → Mohammed-Houcine Saidi-Remili

Nom seul :
- "Beddiaf" ou "Bediaf" → Kaouthar Beddiaf
- "Chatenay" ou "Chatnay" → Yann Chatenay
- "Gousseff" ou "Gousef" ou "Goussef" → Lucas Gousseff
- "Hajji" ou "Haji" ou "Hadji" → Samy Hajji
- "Jaballah" ou "Jabala" ou "Djabala" → Ahmed Jaballah
- "Moulay" ou "Ben Mohand" ou "Mohand" → Mehdi Moulay Ben Mohand
- "Saidi" ou "Remili" ou "Saidi-Remili" → Mohammed-Houcine Saidi-Remili

Nom ecorche :
- Si le patient ecrit quelque chose qui RESSEMBLE a un de ces noms, deviner et confirmer :
  "Vous voulez dire Samy Hajji ? 😊" puis envoyer le lien si oui.
- Si doute entre 2 kines, demander : "On a Ahmed Jaballah et Mehdi Moulay, 
  c'est lequel que vous cherchez ?"
- Ne jamais dire "je ne connais pas ce nom". Toujours essayer de deviner.

SPECIALITES : musculosquelettique, sportive, respiratoire, neurologique,
pediatrique, rhumatologie, post-operatoire, traumatologie, et toutes les
specialites courantes de kinesitherapie.

ON NE FAIT PAS : soins a domicile, uro-gynecologie, enfants de moins de 10 ans
"""

INSTRUCTIONS_BOT = """
ROLE : Tu es le secretaire du cabinet. Tu es la premiere personne que le patient 
"rencontre" — tu dois lui donner envie de venir. Chaleureux, souriant, bienveillant.
Tu VOUVOIES mais avec de la chaleur humaine, pas du formalisme froid.

TON : Comme une personne a l'accueil qui sourit quand elle repond. Pas un robot 
administratif. Tu es content d'aider. Tu rassures. Tu mets a l'aise.
Exemples de ton :
- "Avec plaisir !" plutot que "D'accord."
- "Pas de souci du tout !" plutot que "C'est note."
- "On vous attend !" plutot que "Prenez RDV sur Doctolib."
- "N'hesitez surtout pas si vous avez d'autres questions 😊" plutot que 
  "Puis-je vous aider pour autre chose ?"

LONGUEUR : 2-4 lignes max. Court mais chaleureux.
EMOJIS : 1-2 par message, ca rend le ton plus humain. Pas plus.

=== COMMENT REPONDRE ===

PRISE DE RDV :
- D'abord demander : "Vous etes deja suivi(e) au cabinet ou c'est un premier RDV ? 😊"

NOUVEAU PATIENT (1er RDV) :
- Ne PAS aider a choisir un kine. Ne PAS demander avec qui.
- Juste orienter vers Doctolib de facon simple :
  "Pour un premier rendez-vous, rendez-vous sur Doctolib et cherchez
  'kinesitherapeute Argenteuil', vous trouverez nos kines avec leurs dispos ! 😊"
- Si le patient insiste ou demande un nom → on peut donner la liste des prenoms
  mais sans recommander : "Nos kines sont Kaouthar, Yann, Lucas, Samy, Ahmed,
  Mehdi et Houcine. Vous pouvez voir leurs dispos sur Doctolib !"

PATIENT DEJA SUIVI (deja venu au cabinet) :
- Demander avec quel kine il est suivi : "Vous etes suivi(e) par quel
  kinesitherapeute ? 😊"
- Si le patient donne un nom → envoyer le lien Doctolib direct de ce kine.
  Ex : "Voila le lien pour prendre RDV avec Samy Hajji : [lien].
  Vous pouvez choisir le creneau qui vous arrange !"
- Si nom ecorche → deviner et confirmer, puis envoyer le lien.

DANS TOUS LES CAS :
- Si veut par telephone : "Je comprends ! Malheureusement on ne peut pas prendre les
  RDV par telephone. Mais rendez-vous sur Doctolib, c'est tres rapide !"
- Ne JAMAIS donner tous les liens Doctolib d'un coup.

ANNULATION / REPORT :
- D'abord demander avec quel kine : "Vous aviez RDV avec quel kinesitherapeute ?"
- Puis orienter : "Vous pouvez annuler ou deplacer directement depuis Doctolib."
- Si Doctolib bloque (moins de 24h) : "Pas de souci du tout, ne vous inquietez pas ! 😊
  Ce n'est pas grave. Quand vous le souhaitez, vous pouvez reprendre un nouveau creneau 
  sur Doctolib." Etre rassurant. JAMAIS culpabiliser.
- Proposer de reprendre : "Vous souhaitez reprendre un prochain RDV ? Je peux vous 
  envoyer le lien Doctolib de votre kine."
- Si n'y arrive pas : "Donnez-moi votre nom et le creneau concerne, je transmets a 
  votre kine."

ADRESSE / ACCES :
- Le cabinet est situe SUR LA PLACE D'ALEMBERT, pas au pied de l'immeuble.
- Dire au patient de se garer a proximite, il existe un parking souterrain.
- Prendre les escaliers qui menent a la place.
- En face d'une geante fresque avec la Tour Eiffel, vous ne pouvez pas la rater.
- Si le patient dit "je ne trouve pas", "je suis perdu", "c'est ou exactement" :
  donner ces indications etape par etape, calmement et avec bienveillance.

TARIFS / REMBOURSEMENT :
- "Nous sommes conventionnes secteur 1, sans depassement."
- "Avec une ordonnance, vos seances sont prises en charge par la Secu. Le complement
  depend de votre mutuelle."
- "Pensez a apporter ordonnance et carte Vitale au premier RDV."

SPECIALITES :
- Si on pratique -> confirmer + Doctolib
- Si domicile -> "Nous ne faisons pas de soins a domicile, uniquement au cabinet."
- Si uro-gyneco -> "Nous ne pratiquons pas cette specialite. Je vous recommande de
  chercher un kine specialise sur Doctolib."
- Si enfant de moins de 10 ans -> "Nous ne prenons pas en charge les enfants de moins
  de 10 ans. Je vous recommande de chercher un kine pediatrique sur Doctolib."

URGENCE / DOULEUR :
- Moderee : "Prenez un RDV rapidement sur Doctolib."
- Grave / trauma : "Consultez un medecin ou rendez-vous aux urgences. Nous pourrons
  vous accompagner en reeducation ensuite avec une ordonnance."

ORDONNANCE :
- "Une ordonnance de kine est valable 1 an."
- "Pensez a apporter ordonnance + carte Vitale."

PREMIER MESSAGE :
- Si juste "Bonjour" -> "Bonjour ! 😊 Cabinet de Kinesitherapie du Val d'Argenteuil.
  Pour prendre RDV, annuler ou modifier, rendez-vous sur Doctolib.
  Si vous avez la moindre question, n'hesitez pas, on est la !"
- Sinon reponds a ce que le patient dit, toujours avec chaleur.

NOM DU PATIENT :
- Si le patient donne son nom dans la conversation (ex: "c'est Mme Dupont", 
  "je suis M. Martin", "au nom de Leroy"), retiens-le et utilise-le dans tes reponses.
- Ne demande pas le nom systematiquement. Mais si le patient veut annuler ou transmettre
  un message, demande naturellement : "C'est a quel nom ?"

=== CE QUE TU NE FAIS JAMAIS ===
- Donner un diagnostic ou avis medical
- Promettre un creneau (tu ne vois pas l'agenda)
- Donner les numeros perso des kines
- Partager des infos sur d'autres patients
- Mentionner que tu es un bot ou une IA
- Tutoyer un patient
- Messages de plus de 4 lignes
- JAMAIS dire "rappeler", "nous rappeler", "recontacter par telephone", "appeler le cabinet"
  On ne repond JAMAIS au telephone. Toujours orienter vers SMS, WhatsApp ou Doctolib.
- JAMAIS dire au patient de "reessayer plus tard" par telephone
"""

# ============================================================
# CONVERSATIONS
# ============================================================

conversations = {}

KINES = {
    "kaouthar": "Kaouthar Beddiaf",
    "beddiaf": "Kaouthar Beddiaf",
    "kawtar": "Kaouthar Beddiaf",
    "kaoutar": "Kaouthar Beddiaf",
    "yann": "Yann Chatenay",
    "yan": "Yann Chatenay",
    "chatenay": "Yann Chatenay",
    "lucas": "Lucas Gousseff",
    "gousseff": "Lucas Gousseff",
    "goussef": "Lucas Gousseff",
    "gousef": "Lucas Gousseff",
    "samy": "Samy Hajji",
    "sami": "Samy Hajji",
    "sammy": "Samy Hajji",
    "hajji": "Samy Hajji",
    "haji": "Samy Hajji",
    "hadji": "Samy Hajji",
    "ahmed": "Ahmed Jaballah",
    "ahmad": "Ahmed Jaballah",
    "jaballah": "Ahmed Jaballah",
    "jabala": "Ahmed Jaballah",
    "mehdi": "Mehdi Moulay Ben Mohand",
    "mehdy": "Mehdi Moulay Ben Mohand",
    "moulay": "Mehdi Moulay Ben Mohand",
    "mohand": "Mehdi Moulay Ben Mohand",
    "houcine": "Mohammed-Houcine Saidi-Remili",
    "houssine": "Mohammed-Houcine Saidi-Remili",
    "hussein": "Mohammed-Houcine Saidi-Remili",
    "saidi": "Mohammed-Houcine Saidi-Remili",
    "remili": "Mohammed-Houcine Saidi-Remili",
}

def detect_kine(message):
    """Detecte quel kine est mentionne dans le message."""
    m = message.lower()
    for keyword, name in KINES.items():
        if keyword in m:
            return name
    return None

def extract_patient_name(message):
    """Essaye d'extraire le nom du patient du message."""
    import re
    patterns = [
        r"(?:je suis|c'est|au nom de|nom de|je m'appelle|moi c'est)\s+(?:m(?:me|adame|onsieur|r)?\.?\s+)?([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)?)",
        r"(?:je suis|c'est)\s+([A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)?)",
    ]
    for p in patterns:
        match = re.search(p, message)
        if match:
            return match.group(1).strip()
    return None

def get_conv(phone):
    if phone not in conversations:
        conversations[phone] = {
            "messages": [], "created_at": datetime.now().isoformat(),
            "last_at": datetime.now().isoformat(), "type": "unknown",
            "kine": None, "patient_name": None,
        }
    return conversations[phone]

def add_msg(phone, role, content):
    c = get_conv(phone)
    c["messages"].append({"role": role, "content": content, "ts": datetime.now().isoformat()})
    c["last_at"] = datetime.now().isoformat()
    if role == "user":
        # Tracker le kine mentionne
        kine = detect_kine(content)
        if kine:
            c["kine"] = kine
        # Tracker le nom du patient
        name = extract_patient_name(content)
        if name:
            c["patient_name"] = name
    return c

# ============================================================
# INTELLIGENCE CLAUDE
# ============================================================

def generate_response(phone, user_msg):
    c = get_conv(phone)
    msgs = []
    if len(c["messages"]) == 0:
        msgs.append({"role": "user", "content": f'Un patient ecrit au cabinet : "{user_msg}"\nReponds comme le secretaire. Court, pro, vouvoiement.'})
    else:
        for m in c["messages"][-10:]:
            msgs.append({"role": m["role"] if m["role"] in ["user","assistant"] else "user", "content": m["content"]})
        msgs.append({"role": "user", "content": user_msg})
    try:
        r = claude_client.messages.create(model="claude-sonnet-4-20250514", max_tokens=250,
            system=f"{CONTEXTE_CABINET}\n\n{INSTRUCTIONS_BOT}", messages=msgs)
        return r.content[0].text
    except Exception as e:
        print(f"Erreur Claude: {e}")
        return "Bonjour ! 😊 Cabinet de Kinesitherapie du Val d'Argenteuil. Pour prendre RDV, direction Doctolib ! Et si vous avez des questions, on est la, ecrivez-nous !"

# ============================================================
# DETECTION + ALERTES
# ============================================================

def detect_type(msg):
    m = msg.lower()
    if any(k in m for k in ["urgence","urgent","tres mal","bloque","coince","tombe","fracture","chute"]): return "urgence"
    if any(k in m for k in ["annuler","annulation","reporter","deplacer","decaler","plus venir"]): return "annulation"
    if any(k in m for k in ["rendez-vous","rdv","reserver","prendre","disponibilite","creneau","dispo"]): return "rdv"
    if any(k in m for k in ["horaire","heure","ouvert","adresse","ou","tarif","prix","combien","parking"]): return "info"
    return "autre"

def send_alert(phone, rtype, msg):
    alerts = {"urgence": f"🚨 URGENCE patient !\n{phone}\n\"{msg}\"", "annulation": f"📋 Annulation :\n{phone}\n\"{msg}\""}
    if rtype not in alerts: return
    try: twilio_client.messages.create(body=alerts[rtype], from_=TWILIO_WHATSAPP_NUMBER, to=ALERT_NUMBER)
    except Exception as e: print(f"Erreur alerte: {e}")

# ============================================================
# WEBHOOK SMS & WHATSAPP
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming = request.values.get("Body", "").strip()
    from_num = request.values.get("From", "")
    if not incoming or not from_num: return "OK", 200
    ch = "whatsapp" if from_num.startswith("whatsapp:") else "sms"
    print(f"[{datetime.now()}] [{ch}] {from_num}: {incoming}")
    add_msg(from_num, "user", incoming)
    rtype = detect_type(incoming)
    get_conv(from_num)["type"] = rtype
    if rtype in ["urgence","annulation"]: send_alert(from_num, rtype, incoming)
    bot_resp = generate_response(from_num, incoming)
    add_msg(from_num, "assistant", bot_resp)
    resp = MessagingResponse()
    resp.message(bot_resp)
    return str(resp)

# ============================================================
# WEBHOOK APPEL -> MESSAGE VOCAL + AUTO-SMS
# ============================================================

@app.route("/voice", methods=["POST"])
def voice_webhook():
    from_num = request.values.get("From", "")
    if not from_num: return "OK", 200
    print(f"[{datetime.now()}] [APPEL] {from_num}")
    sms = "Bonjour ! 😊 C'est le Cabinet de Kinesitherapie du Val d'Argenteuil.\n\nMerci d'avoir appele ! Pour prendre RDV, annuler ou modifier un rendez-vous, rendez-vous sur Doctolib.\n\nSi vous avez la moindre question, ecrivez-nous ici par SMS, on vous repond avec plaisir !"
    try:
        twilio_client.messages.create(body=sms, from_=TWILIO_PHONE_NUMBER, to=from_num)
        add_msg(from_num, "assistant", f"[AUTO-SMS] {sms}")
    except Exception as e: print(f"Erreur SMS: {e}")
    voice = VoiceResponse()
    voice.say("Bonjour, vous etes bien au cabinet de kinesitherapie du val d'Argenteuil. Vous allez recevoir un SMS afin de discuter avec notre secretariat. A tres bientot !", language="fr-FR", voice="alice")
    return str(voice)

# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard", methods=["GET"])
def dashboard():
    s = [{"phone":p,"type":c["type"],"kine":c.get("kine","?"),"msgs":len(c["messages"]),"last":c["last_at"]} for p,c in conversations.items()]
    return json.dumps(s, indent=2, ensure_ascii=False), 200, {"Content-Type":"application/json"}

# ============================================================
# RESUME QUOTIDIEN PAR KINE
# ============================================================

ALL_KINES = [
    "Kaouthar Beddiaf", "Yann Chatenay", "Lucas Gousseff",
    "Samy Hajji", "Ahmed Jaballah", "Mehdi Moulay Ben Mohand",
    "Mohammed-Houcine Saidi-Remili"
]

# Types pertinents pour le resume (on ignore les questions info generales)
TYPES_PERTINENTS = ["rdv", "annulation", "urgence"]

def get_daily_data():
    """Collecte les conversations du jour, filtrees par pertinence."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    by_kine = {k: [] for k in ALL_KINES}
    urgences_sans_kine = []
    
    for phone, conv in conversations.items():
        if not conv["last_at"].startswith(today):
            continue
        
        # Ignorer les conversations "info" et "autre" (questions generales)
        if conv["type"] not in TYPES_PERTINENTS:
            continue
        
        patient_msgs = [m["content"] for m in conv["messages"] 
                       if m["role"] == "user" and m["ts"].startswith(today)]
        if not patient_msgs:
            continue
        
        is_call = any("[AUTO-SMS]" in m["content"] for m in conv["messages"])
        
        entry = {
            "patient": conv.get("patient_name") or "Inconnu",
            "phone": phone.replace("whatsapp:", "").replace("+33", "0"),
            "type": conv["type"],
            "canal": "📞" if is_call else ("📱" if "whatsapp" in phone else "💬"),
            "resume": patient_msgs[0][:80],
        }
        
        kine = conv.get("kine")
        
        if kine and kine in by_kine:
            by_kine[kine].append(entry)
        elif conv["type"] == "urgence":
            # Urgence sans kine → ira chez TOUS les kines
            urgences_sans_kine.append(entry)
        # Sinon on ignore (rdv sans kine = pas pertinent pour un kine specifique)
    
    return by_kine, urgences_sans_kine


def build_kine_summary(kine_name, entries, urgences_communes):
    """Construit le resume pour UN kine."""
    all_entries = entries + urgences_communes
    if not all_entries:
        return None  # Rien a envoyer
    
    date = datetime.now().strftime("%d/%m/%Y")
    prenom = kine_name.split()[0]
    
    lines = [f"📋 Résumé du {date}"]
    lines.append(f"Bonjour {prenom} ! Voici ton récap :\n")
    
    # Compteurs
    nb_rdv = sum(1 for e in all_entries if e["type"] == "rdv")
    nb_annul = sum(1 for e in all_entries if e["type"] == "annulation")
    nb_urg = sum(1 for e in all_entries if e["type"] == "urgence")
    
    counts = []
    if nb_rdv: counts.append(f"📅 {nb_rdv} RDV")
    if nb_annul: counts.append(f"📋 {nb_annul} annulation{'s' if nb_annul > 1 else ''}")
    if nb_urg: counts.append(f"🚨 {nb_urg} urgence{'s' if nb_urg > 1 else ''}")
    lines.append(" | ".join(counts) + "\n")
    
    # Tableau
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    
    type_labels = {"rdv": "📅 RDV", "annulation": "📋 Annul.", "urgence": "🚨 URGENCE"}
    
    for e in entries:
        label = type_labels.get(e["type"], "💬")
        lines.append(f"{e['canal']} {label}")
        lines.append(f"   👤 {e['patient']}")
        lines.append(f"   📞 {e['phone']}")
        lines.append(f"   💬 \"{e['resume']}\"")
        lines.append("──────────────────────")
    
    # Urgences communes (sans kine attribue)
    if urgences_communes:
        lines.append("")
        lines.append("🚨 URGENCES NON ATTRIBUÉES :")
        for e in urgences_communes:
            lines.append(f"   👤 {e['patient']} — 📞 {e['phone']}")
            lines.append(f"   💬 \"{e['resume']}\"")
            lines.append("──────────────────────")
    
    lines.append(f"\nBonne soirée {prenom} 😊")
    
    return "\n".join(lines)


def _send_wa_message(wa_number, message):
    """Envoie un message WhatsApp (decoupe si > 1500 chars)."""
    if len(message) > 1500:
        parts = [message[i:i+1500] for i in range(0, len(message), 1500)]
        for part in parts:
            twilio_client.messages.create(body=part, from_=TWILIO_WHATSAPP_NUMBER, to=wa_number)
    else:
        twilio_client.messages.create(body=message, from_=TWILIO_WHATSAPP_NUMBER, to=wa_number)


def send_kine_summary(kine_name, message):
    """Envoie le resume a un kine par WhatsApp."""
    wa_number = KINE_WHATSAPP.get(kine_name)
    if not wa_number or "XXXX" in wa_number:
        print(f"[RESUME] Pas de numero pour {kine_name}, skip")
        return False
    try:
        _send_wa_message(wa_number, message)
        print(f"[RESUME] Envoye a {kine_name}")
        # Si c'est Houcine, envoyer aussi a Amine (meme contenu, shadow)
        if kine_name == "Mohammed-Houcine Saidi-Remili":
            try:
                _send_wa_message(WA_AMINE_SHADOW, message)
                print(f"[RESUME] Shadow envoye a Amine")
            except Exception as e2:
                print(f"[RESUME] Erreur shadow Amine: {e2}")
        return True
    except Exception as e:
        print(f"[RESUME] Erreur pour {kine_name}: {e}")
        return False


@app.route("/resume", methods=["GET", "POST"])
def daily_resume():
    """
    GET  → affiche tous les resumes dans le navigateur
    POST → envoie chaque resume au kine concerne par WhatsApp
           (appeler via cron tous les soirs a 20h)
    """
    by_kine, urgences = get_daily_data()
    
    if request.method == "POST":
        sent = 0
        skipped = 0
        for kine_name in ALL_KINES:
            summary = build_kine_summary(kine_name, by_kine[kine_name], urgences)
            if summary:
                if send_kine_summary(kine_name, summary):
                    sent += 1
            else:
                skipped += 1
        # Envoyer aussi un recap global a toi
        global_summary = f"📊 Résumés envoyés : {sent} kinés notifiés, {skipped} sans activité."
        try:
            twilio_client.messages.create(body=global_summary, from_=TWILIO_WHATSAPP_NUMBER, to=ALERT_NUMBER)
        except: pass
        return f"Envoye a {sent} kines, {skipped} sans activite", 200
    
    # GET → afficher dans le navigateur
    html = f"<h2>Résumés du {datetime.now().strftime('%d/%m/%Y')}</h2>"
    for kine_name in ALL_KINES:
        summary = build_kine_summary(kine_name, by_kine[kine_name], urgences)
        if summary:
            html += f"<h3>{kine_name}</h3><pre>{summary}</pre><hr>"
        else:
            html += f"<h3>{kine_name}</h3><p><em>Rien à signaler</em></p><hr>"
    return html, 200

if __name__ == "__main__":
    print("🏥 Bot Secretaire — Cabinet Kine Val d'Argenteuil")
    print("📡 /webhook (SMS+WhatsApp) | 📞 /voice (Appels)")
    print("📊 /dashboard | 📋 /resume (resume quotidien)")
    app.run(debug=True, port=5000)
