import os

# Settings exige a chave do embaralhamento; os testes usam uma fixa.
os.environ.setdefault("APP_CODE_SECRET", "chave-de-teste-com-16+-caracteres")
