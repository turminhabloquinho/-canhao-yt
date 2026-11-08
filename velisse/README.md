# Velisse no GitHub (substitui o Make)

O GitHub guarda o código e, com o **GitHub Actions**, roda esse código sozinho nos computadores dele, de graça
(2.000 min/mês em repositório privado; ilimitado em público). Não depende do seu PC nem do Make.

| Robô | Quando roda | O que faz |
|---|---|---|
| `Velisse - publicar Short` | quando você manda (botão **Run workflow**) ou quando um `N.mp4` entra em `velisse/fila/` | lê a linha N da aba *Fila de Videos*, envia o vídeo ao YouTube como privado com horário marcado (coluna B, horário de Nova York), marca como conteúdo de IA e grava o ID na coluna J |
| `Velisse - copiar vendas do Stripe` | de hora em hora | copia cada venda paga nova para *Respostas ao formulário 1* (sem duplicar; coluna H leva o `plink_` para o Painel achar o fornecedor) |

A geração dos vídeos continua manual no Flow (decisão "a").

## Configuração (1 vez, ~15 min) — só você pode fazer

1. **Token do Google** (conta glownest.business10, dona do canal):
   - Google Cloud Console → o mesmo projeto do Bloquinho → ativar *YouTube Data API v3* e *Google Sheets API*.
   - Baixar o cliente OAuth (tipo "Desktop") como `velisse/client_secret.json` no seu PC.
   - `pip install google-api-python-client google-auth-oauthlib` e `python velisse/velisse_bot.py auth`.
   - Copiar o conteúdo de `velisse/token.json`.
2. **Chave do Stripe**: Stripe → Developers → API keys → *Create restricted key* → só **Checkout Sessions: Read** → copiar `rk_live_...`.
3. **GitHub** → repositório → Settings → Secrets and variables → Actions → *New repository secret*:
   - `VELISSE_GOOGLE_TOKEN` = conteúdo do token.json
   - `STRIPE_API_KEY` = a chave restrita
4. Teste: Actions → *Velisse - copiar vendas do Stripe* → Run workflow. Deu verde? Pode desligar os cenários do Make.

Nunca coloque token, client_secret ou chave dentro dos arquivos do repositório — só em Secrets.

## Uso diário
- Eu gero os vídeos no Flow, preencho a fila e disparo *Velisse - publicar Short* com N e o link do vídeo.
- Ou você sobe `15.mp4` para `velisse/fila/` (Add file → Upload) e ele publica sozinho a linha 15.
