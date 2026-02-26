# Blog topics — ConceptDoc

Argomenti emersi durante lo sviluppo del progetto, da usare come base per post del blog.

---

## 1. Perché la documentazione tradizionale non basta per l'AI

**Angolo:** Il problema che ConceptDoc risolve.
Il codice dice *cosa* fa il sistema. Non dice *perché* certi vincoli esistono, *cosa* succede nei casi limite, o *quale* era l'alternativa scartata. Un AI che legge il codice senza questo contesto fa errori sottili: rimuove un vincolo che sembra ridondante, semplifica un pattern che ha una ragione precisa, genera codice che passa i test ma viola le regole di business.

**Punti chiave:**
- Il problema dello "scultore cieco" (AI velocissimo ma senza visibilità sul risultato)
- Documentazione tradizionale: scritta per umani, inutile per AI
- Cosa serve davvero: tensioni architetturali, flussi attesi, test concettuali

---

## 2. Il concetto di "tensione architetturale"

**Angolo:** La sezione più importante di un `.cdoc`.
Una tensione non è un commento. È la documentazione di una scelta che sembra sbagliata ma non lo è — o di un vincolo che non deve essere toccato senza riconsiderare le sue conseguenze. Esempi reali dal progetto.

**Punti chiave:**
- Differenza tra commento inline e tensione
- Quando una cosa merita una tensione (quando "sembrerebbe ovvio" cambiarla)
- Esempi concreti: atomic write, ID non riusabili, parser CLI intenzionalmente semplice
- Il concetto di ADR (Architecture Decision Record) inline e leggero

---

## 3. Test concettuali: il layer di spec che sopravvive ai refactor

**Angolo:** La parte più originale di ConceptDoc.
I test unitari testano l'implementazione. I test concettuali testano l'intento. Quando cambi framework, rinomini un metodo o riscrivi una classe, i test unitari si rompono — i test concettuali no. Sono la spec, non il test.

**Punti chiave:**
- Differenza tra test unitario e test concettuale
- Language-agnostic: funzionano in Python, JS, Go, ovunque
- Come usarli per generare test con un agente AI (`generate-tests` prompt)
- Esempi dal progetto todo: lifecycle, validation, persistence

---

## 4. ConceptDoc vs le alternative: JSDoc, docstrings, OpenAPI, ADR

**Angolo:** Posizionamento nello spazio degli strumenti esistenti.
Non è un rimpiazzo, è un complemento. Cosa fa che gli altri non fanno, cosa lascia agli altri.

**Punti chiave:**
- JSDoc/docstrings: documentano la firma, non i vincoli
- OpenAPI: ottimo per contratti HTTP, nulla sull'implementazione interna
- ADR: giusto livello di astrazione ma non è collegato al codice
- ConceptDoc: file-level, vive accanto al codice, minimo

---

## 5. CLAUDE.md + .cdoc: come strutturare il contesto per un agente AI

**Angolo:** Layer operativo — come si usa ConceptDoc nella pratica con un coding agent.
ConceptDoc da solo non basta. Serve anche dirgli all'agente come comportarsi. CLAUDE.md è il layer di istruzioni permanenti, `.cdoc` è il contesto per file. Insieme coprono tutto.

**Punti chiave:**
- CLAUDE.md: istruzioni operative (leggi il .cdoc prima di modificare, non violare le tensioni)
- `.cdoc`: contesto semantico per file
- Prompt riutilizzabili: generate-tests, review-tensions, sync-cdoc
- Il workflow completo: modifica → sync-cdoc → genera test → review-tensions

---

## 6. Da 200 righe di JSON a 30 righe di YAML: l'evoluzione dello standard

**Angolo:** La storia del progetto e la lezione imparata.
ConceptDoc è nato come schema JSON verboso con metadata, components, pre/postconditions, testFixtures, businessLogic, aiNotes. Era completo e formale. Era anche inutilizzabile. Questo post racconta la ridefinizione e cosa si guadagna rimuovendo.

**Punti chiave:**
- Il problema del "overhead di manutenzione"
- Cosa è stato rimosso e perché (ridondante con codice o git)
- Cosa è rimasto e perché (tensioni, test concettuali, workflows)
- La regola: se devi aggiornarlo ogni volta che cambia l'implementazione, non vale la pena averlo

---

## 7. Come scrivere un buon .cdoc: guida pratica

**Angolo:** Tutorial hands-on.
Con esempi reali dal progetto todo. Cosa mettere, cosa evitare, come scegliere cosa documentare.

**Punti chiave:**
- La domanda guida: "cosa sorprenderebbe un AI che legge questo file?"
- Come identificare le tensioni nel proprio codice
- Come scrivere test concettuali utili (non ovvi, non banali)
- Red flags: file troppo lungo, sezioni vuote, contenuto che replica il codice

---

## 8. ConceptDoc per team: come mantenerlo in sync con il codice

**Angolo:** Il problema del "doc che invecchia" e come affrontarlo.
Il rischio principale di qualsiasi documentazione parallela è che diventi obsoleta. Strategie pratiche per evitarlo.

**Punti chiave:**
- Il prompt `sync-cdoc`: dopo ogni modifica significativa
- Git hook: avviso quando `.py` cambia senza toccare `.cdoc`
- Review delle tensioni come parte del code review
- Il segnale d'allarme: se il `.cdoc` non è cambiato in mesi, probabilmente è stale
