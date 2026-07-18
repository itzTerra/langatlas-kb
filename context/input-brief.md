# Project Hermes — Brainstorm Input Brief

> Working document: the complete raw input for the design brainstorm. Combines (a) the original
> Notion page content (verbatim in meaning, restructured) and (b) the owner's constraints and
> directions given in conversation. Subagents: treat this as the single source of truth about
> intent. Do not invent requirements beyond it; flag gaps instead.

## 1. Project idea (from Notion page "Project Hermes")

### Terminology

- **concept** — loosely defined as any idea or principle, often (but not necessarily) based on or utilised in theory
- **feature** — a realisation of a concept within the context of a family of related systems (in this case, programming languages)
- **feature instance** — a realisation of a feature in a specific system (in this case, a particular language)
- **characteristic** — an observable property of a system or feature instance

### Modules

#### Knowledge Base

- Concrete features of different programming languages explained with their different types and languages they are used in
  - name and preview of syntax of each feature implementation in each language
  - impact of feature type on qualities: practicality/efficiency, performance, ease of use / learnability / beginner friendliness, reliability, compiler/interpreter complexity
    - "Other factors of potential importance include platform compatibility, development tool support, documentation, training materials, user community, and nonfunctional properties" — Jordan et al. (2015)
    - "the values of the features in the model could be determined as functions of the domain characteristics. Approximations of these functions could perhaps be obtained empirically, by studying feature usage in existing applications or by experimenting with toy problems." — Jordan et al. (2015)
  - feature type (functionality) must be separate from its syntax
  - ranked by upvotes + usage rate in the builder
  - similarity to other feature types
  - required, impossible or problematic combination validation
- Language detail with a structured view of its features with syntax
- Language statistics (TIOBE…)
- Extremely easy and visible contribution options:
  - link to GitHub discussion/thread under each feature and language
  - contribution guide
  - source code link for every bit of info on the site
- new private/public feature/feature type/syntax definition

#### Programming Language Builder + Public Language Library

PC part builder, BUT with programming language features to build your dream programming language.

- features ordered by usage rate and mined language data from knowledge base
- community rated submissions (public, private) → usage rate of selected components
- comments and github repo links for the submitted built language with possible implementations on the submissions
- preview of THE CODE language made of top rated components of all categories by the system

#### Programming Language Selector

Use knowledge base to recommend a popular programming language (for workforce) for the particular domain.

#### Explicitly marked UNREALISTIC parts (out of scope)

- auto language standard from components
- auto compiler from components
- translator modules for automatic conversion between languages based on the knowledge base

### Architecture notes (from Notion)

FEATURES = language dimensions, language features, language constructs, language mechanisms, computation models, semantic concepts, design dimensions.

#### Layers

1. **Syntax**
2. **Semantic features** (mostly checkboxable):
   - pattern matching
   - indexed collections: tuple, array, record, dictionary (extensible), extensible array (vector)
   - unindexed collections: list, stream
   - algebraic data types
   - strings (unicode support)
   - interfaces/traits: method profiles, methods with defaults
   - effect handlers
   - higher-order programming:
     - first-class functions — with sub-abilities: Procedural abstraction (convert any statement into a procedure value); Genericity (pass procedure values as arguments); Instantiation (return procedure values as results); Embedding (put procedure values in data structures)
     - first-class classes (classes as values)
     - full lexical scoping: nested functions, nested classes
     - first-class messages (method calls as values)
   - coroutines
   - reflection
   - metaprogramming
     - metaclass — "A metaclass is a class with a particular set of methods that correspond to the basic operations of a class, for example: object creation, inheritance policy (which methods to inherit), method call, method return, choice of method to call, attribute assignment, attribute access, self call. Writing these methods allows to customize the semantics of objects." (Van Roy & Haridi 2003, https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf)
   - atomics
   - dataflow concurrency — "If an operation tries to use a variable that is not yet bound, the operation will simply wait. Perhaps some other thread will bind the variable, and then the operation can continue."
   - standard library: RNG, sort
   - message passing (method definition) — "messages are records and method heads are patterns that match a record" (Van Roy & Haridi 2003)
     - records (messages): static, dynamic
     - fixed argument list, flexible argument list
     - variable reference to method head
     - optional argument
     - private method label, dynamic method label
     - the otherwise method (enables forwarding and delegation)
   - first-class attributes (Van Roy & Haridi 2003)
   - static and dynamic binding
   - information hiding scopes: private, public, protected
   - active objects (Van Roy & Haridi 2003)
3. **Design choices** (mostly mutually exclusive):
   - Paradigm: functional, OOP, logic
   - Typing: static, dynamic, gradual, dependent, affine, linear, structural, nominal
   - Type Equivalence
   - Evaluation strategy: eager (strict), nonstrict, lazy
   - Parameter passing: call-by-value, call-by-reference, call-by-variable, call-by-value-result, call-by-name, call-by-need
   - Sequential Control
   - Memory management: manual, tracing GC, ARC, ownership, regions
   - Concurrency model: threads, green threads, actors, CSP, async/await, software transactional memory, dataflow concurrency
   - ADTs (Van Roy & Haridi 2003): open declarative unbundled; secure declarative unbundled; secure declarative bundled; secure stateful bundled; secure stateful unbundled
   - Module systems: files, namespaces, packages, modules, functors, traits, mixins
   - Effects: none, algebraic
   - Polymorphism: subtyping, parametric, ad-hoc, row
   - Encapsulation: no, yes, with capabilities
   - Inheritance: single, multiple
   - Dispatch: single, multiple
   - Purity: pure, impure
   - Exceptions: checked, unchecked, effect system
   - Macros: none, textual, AST, hygienic
   - IO
4. **Emergent interactions** — multiple selected features can probably enforce or forbid a different feature.

#### Concepts deliberately excluded from the feature model (hard to atomize; excluded to maximize composability)

- **Scope** — Van Roy & Haridi define scope as the "part of the program text in which [a] member is visible". Usually expressed via specific language constructs; hard to compare between languages.
- **Exceptions** — a runtime failure/exception is "an unexpected condition that cannot be handled locally". Rules for definition, propagation, recovery are context-dependent; a cross-cutting concern.
- **Security** — "protection from both malicious computations and innocent (but buggy) computations"; a global system property, typically implemented by compiler/interpreter/VM/OS.
- **Naming** — e.g. Haskell's pattern-matching naming cuts across multiple feature groups (type systems, declarative expressions).

(An attached PDF `feature-model.pdf` exists on the Notion page — the Jordan et al. (2015) feature model paper.)

#### Graph representation idea

Features as **nodes in a typed graph**. Each node is a semantic concept; edges capture relationships:

- **requires** (ownership → move semantics)
- **enables** (pattern matching → expressive destructuring)
- **influences** — positively / negatively (e.g., algebraic data types strongly encourage pattern matching)
- **conflicts with** (where applicable)
- **alternative to** (GC ↔ ownership as memory management strategies)
- **implemented by** (languages supporting the concept)
- **expressed as** (syntax in each language)
- **improves quality** (memory safety improves reliability)
- **hurts quality** (ownership hurts learnability)

> "This is almost like a package manager. Think Cargo. Instead of packages, you're selecting language concepts."

No value judgements on presence/absence of features in the model itself: "the value of a given feature is inherently application-dependent; 'the simple presence of features is not a good indication of the worth of a language'" (Jordan et al. 2015, citing https://onlinelibrary.wiley.com/doi/10.1002/spe.4380110102). A full-featured language allows a wider range of programs to be concisely expressed, but at the cost of a more expensive implementation and a more challenging learning curve.

#### Sources listed on the Notion page

- Dirty Programming Language Features: http://pldb.info/
- AI Programming Language Comparisons: https://lang-compare.zander.wtf/ and https://programming-languages.com/
- Wikidata: https://www.wikidata.org/wiki/Q2005 ; influence network: https://programminglanguages.info/influence-network/#
- Manual language comparisons: https://hyperpolyglot.org/
- DSL generators: https://spoofax.dev/ , https://eclipse.dev/Xtext/
- Van Roy & Haridi, *Concepts, Techniques, and Models of Computer Programming* (2003): https://webperso.info.ucl.ac.be/~pvr/VanRoyHaridi2003-book.pdf
- Jordan et al. (2015) — feature model paper (PDF attached in Notion)

## 2. Owner constraints & directions (from conversation)

1. **Knowledge base for agents** = vector database for RAG. Every user-facing fact needs a source. A fact must link to its source; a source must have a structured identification format (some kind of .bib — most universal/modern preferred).
2. **Developer must be able to connect the RAG system to Claude Code**, and ideally other providers, e.g. local models.
3. Source identification does not need to live in the vector DB itself — it can be in a normal DB — but it will be used in the user-facing app (users see where each piece of info came from).
4. **AI agents managed by the developer** use the knowledge base + their own knowledge to argue about the project topic, and add more sources to the knowledge base backing their arguments. Incrementally this should lead to a self-backing net of information covering the project's scope (mapping many, many languages to structured programming-language concepts).
5. **Facts must be easily challengeable by human experts** who know better than AI agents. Two candidate solutions:
   - (a) All info as static human-readable YAML-like files (doesn't have to be YAML) on GitHub; feedback happens through GitHub. Pros: minimum effort, programmers already familiar. Cons: facts live as static files on GitHub (space concerns), or must be compiled-and-synced-back somehow between GitHub and the production database.
   - (b) A custom forum module in the app itself.
6. **Website**: SEO-focused, but not a wiki. For human eyes, not an information source for AI agents (the site is built on already existing sources). Clean and pretty design (the opposite of Amazon's cluttered look).
7. **Solo developer, proof-of-concept MVP.** Resources: Claude Code Pro subscription; no GPU for local inference; fairly slow AI API for models hosted by the owner's university. Need the best developer lifecycle for this situation. One idea: make an agent an expert for a particular language (for all supported languages) and let them argue between themselves to decide on the programming-language feature model that fits all languages and most experts agree on.
8. **No architecture decided.** Must brainstorm all needed services and all problems to be faced.
9. Owner asked to be prompted about any important missed angle that needs clearing up.

## 3. Deliverable of the brainstorm phase

A single source-of-context `.md` (probably `CLAUDE.md`) replacing the Notion page, linking to specialized `.md` files in a context dir. Unified formatting (one citation style). Must preserve ALL Notion info (reformatting/restructuring allowed), plus brainstorm decisions, open questions, and other useful context.
