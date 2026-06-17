# ARQUIVO DE TESTE — APAGAR depois de confirmar que o Bandit funciona.
# Cada trecho abaixo introduz de proposito uma falha conhecida.

import hashlib
import sqlite3

# 1. Senha escrita direto no codigo -> STRIDE: Information Disclosure
password = "admin123"

# 2. Hash fraco (MD5) para senha -> STRIDE: Information Disclosure
def hash_senha(senha):
    return hashlib.md5(senha.encode()).hexdigest()

# 3. SQL montado por concatenacao -> STRIDE: Tampering (SQL injection)
def buscar_usuario(nome):
    conn = sqlite3.connect("lazylist.db")
    query = "SELECT * FROM usuarios WHERE nome = '" + nome + "'"
    return conn.execute(query)

# 4. eval em entrada do usuario -> STRIDE: Elevation of Privilege
def calcular(expressao):
    return eval(expressao)