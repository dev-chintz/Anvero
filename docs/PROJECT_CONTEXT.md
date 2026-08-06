# Project Context — Initial Version

## 1. Document Purpose

This document contains the current project context and key decisions regarding its development. It enables transferring work to another ChatGPT account, another computer, or another AI tool without needing to re-explain the entire concept.

The project will be developed iteratively. Initially, it serves primarily as a practical tool to support daily work, and in the longer term, it may be expanded or transformed into a commercial product.

---

## 2. Project Main Idea

A custom application for supporting online sales and marketplace order management is planned.

The application will ultimately enable, among other things:

* Order retrieval from various platforms,
* Presentation of orders in a single, unified panel,
* Unification of order handling regardless of source,
* Order status management,
* Integration with shipping systems,
* Shipment information transmission,
* Potential integration with invoicing systems,
* Product, inventory, and other process management if needed.

The first integrations being considered are:

* Allegro,
* ERLI.

In the future, additional platforms, carriers, accounting systems, warehouse programs, or other services may be added.

---

## 3. Strategic Assumption

We do not plan to immediately create a full competitor to BaseLinker or replicate all its features.

Ready-made systems have a very large number of integrations and are developed by large teams. Attempting to copy such a solution from the start would be unnecessarily complicated.

The plan is as follows:

1. Identify specific problems occurring in daily work.
2. Create a solution tailored to real needs.
3. Build a small, working application version.
4. Test it on real processes.
5. Expand the system only when a specific need arises.

The application will be developed modularly. Features should not be added solely because BaseLinker or another commercial solution has them.

---

## 4. Possible Commercial Future

At this stage, the main goal is not to sell the application.

The first version aims primarily to:

* Improve work efficiency,
* Save time,
* Reduce error count,
* Organize order handling,
* Serve as a practical development project.

If the application proves effective and other companies have similar needs, later consider:

* Subscription-based access sales,
* Creating a SaaS product,
* Licensing sales,
* Creating versions tailored to specific companies,
* Offering additional modules or integrations.

However, do not design the first version as if it were intended to serve thousands of customers from the start. First, it must work well in a real environment.

---

## 5. Planned Architecture

The preliminary division is as follows:

### Frontend

Frontend will be responsible for:

* Application appearance,
* Views and screens,
* Order display,
* Forms,
* Filtering and search,
* User interaction with the system.

Planned technologies:

* HTML,
* CSS,
* JavaScript.

Code should be well-organized from the start.

Example division:

```text
project/
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
```

Do not place all HTML, CSS, and JavaScript in a single file unless there's a specific reason.

Frontend should be created according to current best practices:

* Correct HTML document structure,
* Semantic elements,
* Appropriate headers,
* Correct forms and labels,
* Basic accessibility,
* Responsive appearance,
* Readable code structure,
* Separation of logic from appearance.

### Backend

Backend will be responsible for:

* Allegro API communication,
* ERLI API communication,
* Order retrieval and processing,
* Data saving,
* Business logic,
* Authorization,
* Communication between frontend and database,
* Future integrations.

Preliminary language under consideration:

* Python.

The exact backend framework will be selected later. Possible solutions include, among others:

* FastAPI,
* Django.

At this stage, do not select technology without prior needs analysis.

### Database

The preliminary planned database:

* PostgreSQL.

The database will store, among other things:

* Orders,
* Products,
* Integration-related data,
* Statuses,
* Shipment information,
* Data needed for application operation.

The exact data model will be designed before implementing the actual features.

---

## 6. Allegro and ERLI Integrations

Integrations should be created as independent modules.

Example concept:

```text
backend/
├── integrations/
│   ├── allegro/
│   └── erli/
```

Each integration should be responsible for communication with a specific platform.

The application should not mix Allegro and ERLI logic directly in one place.

Ultimately, the system should transform data from various platforms to a common internal format.

Example:

```text
Order from Allegro
        ↓
Allegro Module
        ↓
Common Order Format
        ↓
Database and application panel

Order from ERLI
        ↓
ERLI Module
        ↓
Common Order Format
        ↓
Database and application panel
```

Thanks to this, the application user will handle orders in a similar way regardless of the platform.

---

## 7. Shipping Handling

We do not plan to create our own courier systems.

If Allegro or another provider offers the appropriate API, the application will use official API interfaces.

Possible future features:

* Shipment creation,
* Shipping method selection,
* Shipment data retrieval,
* Label retrieval or generation,
* Tracking number transmission,
* Shipment status updates.

Shipping integrations should be added only when they are genuinely needed.

---

## 8. Development Environment

Initially, the application will run locally on the computer.

There is no need to set up a local Apache server.

Planned environment:

* Windows,
* Visual Studio Code or Kiro,
* Python,
* PostgreSQL,
* Git,
* GitHub.

Frontend and backend will run locally on addresses such as:

```text
http://localhost
```

or:

```text
http://127.0.0.1
```

Modern development tools have their own development servers, so there is no need to install Apache solely to run the project locally.

---

## 9. Docker

Docker was discussed as a tool for running the application and its dependencies in organized, isolated environments.

Docker may be useful later as it simplifies:

* Transferring the application between computers,
* Maintaining the same environment versions,
* Running the database,
* Deploying the application to a server.

Docker is not required at the beginning.

Plan:

1. First, run the application natively on the computer.
2. Understand the application's fundamentals.
3. Add Docker later when a specific need arises.

---

## 10. Visual Studio Code and Kiro

Two environments are under consideration:

### Visual Studio Code

Advantages:

* Popular standard,
* Large number of extensions,
* Good documentation,
* Easy GitHub integration,
* Wide support for Python, HTML, CSS, and JavaScript.

### Kiro

Kiro is a separate development environment based on Code - OSS and features advanced AI capabilities.

It can be used as the primary editor instead of standard VS Code.

The project remains editor-independent. The same project folder can be opened in both Kiro and Visual Studio Code.

At a later stage, both solutions should be tested to choose the more comfortable one.

---

## 11. Planned Editor Extensions

Initially, do not install a large number of add-ons.

Potentially useful at the start:

* Python,
* Pylance,
* Prettier,
* ESLint,
* Local site preview extension,
* GitHub integration,
* PostgreSQL tools.

Docker and additional tools can be added later.

Auto-code formatting on save can be enabled.

---

## 12. AI Usage

ChatGPT will be used primarily for:

* Discussing the idea,
* Designing architecture,
* Planning features,
* Creating the data model,
* Explaining code,
* Analyzing problems,
* Designing integrations,
* Code review and improvement.

AI tools working directly in the editor, such as Kiro, can be used later for:

* Implementing specific features,
* Editing multiple files,
* Refactoring,
* Finding bugs,
* Accelerating daily coding work.

Do not generate large project segments without understanding their operation.

Code should be:

* Readable,
* Explained,
* Well-organized,
* Capable of further development.

---

## 13. Git and GitHub

Git will be used for project version control.

Git operates locally on the computer and tracks changes in files.

GitHub will be used as a remote repository storage location.

Basic concepts:

* `commit` — saving a logical work stage to the project history,
* `push` — sending commits to GitHub,
* `pull` — downloading changes from GitHub,
* `clone` — downloading the repository to the computer.

Git does not automatically create a separate version after each change in HTML or another file.

The developer decides when to create a commit.

Example commits:

```text
Added basic login screen

Added order panel structure

Added database connection

Added order retrieval from Allegro
```

Recommended rule:

> After completing a larger, logical work segment, create a commit.

Do not create a single commit covering several weeks of work, but there is no need to create a commit after each single change.

Initially, the free GitHub plan should be sufficient.

The project repository will likely be private.

---

## 14. Project Name or Future Brand

A single consistent name is planned, which can be used for:

* Project,
* Future brand or company,
* GitHub account,
* Email address,
* Website domain,
* Future applications.

The name should:

* Be easy to pronounce,
* Be easy to remember,
* Look good in Polish and English,
* Not limit the project solely to Allegro or order handling,
* Enable development toward other applications,
* Not be confusingly similar to an existing company.

Before selection, check:

* `.pl` domain availability,
* `.com` domain availability,
* GitHub username availability,
* Presence of similar companies,
* Potential conflicts with existing brands.

Do not create accounts or buy domains before checking the name.

---

## 15. Consistent Project Identity

After choosing the name, create:

1. Dedicated email address,
2. GitHub account,
3. Private repository,
4. Project name,
5. Basic organizational structure.

All elements should use the same or similar name.

Example structure:

```text
BrandName
├── GitHub: brandname
├── email: brandname@...
├── domain: brandname.pl
└── project: app-name
```

---

## 16. Preliminary Work Order

After starting work on the computer, act step by step.

Proposed order:

1. Check which ChatGPT account contains the active plan.
2. Transfer this document to the proper account if needed.
3. Choose the brand or project name.
4. Check name availability.
5. Create a dedicated email address if such a decision is made.
6. Create a GitHub account.
7. Create a private repository.
8. Choose between Visual Studio Code and Kiro.
9. Install needed tools.
10. Install and configure Python.
11. Install PostgreSQL.
12. Create a local project folder.
13. Connect the project to GitHub.
14. Create basic frontend and backend structure.
15. Run the first local application version.
16. Only then start Allegro and ERLI API integration.

---

## 17. Development Rules

When creating the project, follow these rules:

* Do not complicate the solution without need,
* Develop the application step by step,
* First, create a small working version,
* Plan each major feature before implementation,
* Maintain readable file structure,
* Separate frontend, backend, and database,
* Do not copy large code segments without understanding,
* Document important decisions,
* Create regular commits,
* Do not add all possible integrations from the start,
* Test features on real processes,
* Choose solutions easy to maintain and expand.

---

## 18. Current Status

At this stage:

* Project concept has been preliminarily discussed,
* Technology direction has been specified,
* Environment configuration has not yet started,
* Repository has not yet been created,
* Brand name has not yet been selected,
* Editor has not been finally chosen,
* Implementation has not yet started.

Next stage:

> After running ChatGPT on the proper account, analyze this document, confirm current assumptions, and start environment configuration step by step.

---

## 19. Instruction for New ChatGPT Chat

After pasting this document, provide the following information:

"This is a document describing the project I want to work on. I want to continue from the development environment preparation stage. Lead me step by step and provide only the next necessary stage, as I will perform the configuration directly on the computer. Do not assume I know programming — explain concepts, but maintain best practices and the project's future expansion possibility."

# Project Documentation

Detailed documentation is in the docs/ directory.

PROJECT_CONTEXT.md – main project vision
MVP.md – scope of the first version
ARCHITECTURE.md – system architecture
DATABASE.md – data model
API.md – API documentation
ROADMAP.md – development plan
DECISIONS.md – history of important decisions