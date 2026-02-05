flowchart TD

U[User]
A[Process Analyst]

M[BPMN Modeler]
V[Validator -Non LLM Based Agent]
R[Reviewer]
UI[Streamlit Viewer]

U --> A

A -->|questions only| U
A -->|process JSON only| M

M --> V
V -->|errors| M
V -->|valid| R

R -->|revise issues only| M
R -->|questions only| U
R -->|final xml only| UI
