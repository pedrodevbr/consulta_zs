"""LLM analysis layer via OpenRouter API.

Analyzes Jira ticket history and comments for each material,
providing recommendations on whether consultations are resolved
and whether new ones should be opened.
"""

import json
import logging

import requests

from config import Config

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Você é um analista técnico de gestão de materiais críticos na Itaipu Binacional.
Sua função é analisar o histórico de consultas JIRA de um material ZS e dar
recomendações objetivas.

Responda SEMPRE em JSON com esta estrutura exata:
{
  "resolvido": true | false | null,
  "acao": "texto curto da ação recomendada",
  "justificativa": "explicação breve",
  "abrir_nova": true | false,
  "confianca": "alta" | "media" | "baixa"
}

Regras:
- "resolvido": true se os comentários indicam que a reposição foi tratada,
  material substituído, ou consulta concluída. false se ainda pendente. null se
  não há informação suficiente.
- "acao": ação concreta (ex: "Aguardar resposta do fornecedor",
  "Fechar consulta — material substituído", "Abrir nova consulta",
  "Ajustar nível de estoque", "Nenhuma ação necessária").
- "abrir_nova": false se já existe consulta aberta e ativa para o mesmo
  material. true somente se não há consulta ou todas estão fechadas/resolvidas.
- Seja conciso. Não repita dados que já estão no contexto.
"""


def _build_user_prompt(material_info: dict, tickets: list[dict]) -> str:
    """Build the user prompt with material data and ticket history."""
    lines = [
        f"## Material: {material_info.get('codigo', '?')} — {material_info.get('descricao', '?')}",
        f"- Dias desde quebra: {material_info.get('dias_quebra', '?')}",
        f"- Estoque livre: {material_info.get('estoque', '?')}",
        f"- LMR: {material_info.get('lmr', '?')}",
        f"- Aplicações: {material_info.get('aplicacoes', '—')}",
        f"- Todas localizações desativadas: {material_info.get('all_desat', False)}",
        f"- Ordem planejada: {material_info.get('ordem_planejada', '—')}",
        "",
    ]

    if not tickets:
        lines.append("Nenhum ticket JIRA encontrado para este material.")
    else:
        lines.append(f"## Tickets JIRA ({len(tickets)}):")
        for t in tickets:
            lines.append(f"\n### {t['key']} — Status: {t['status']}")
            lines.append(f"Resumo: {t['summary']}")
            lines.append(f"Responsável: {t['assignee']}")
            lines.append(f"Criado: {t['created'][:10]}  |  Atualizado: {t['updated'][:10]}")
            if t.get("description"):
                desc = t["description"][:300]
                lines.append(f"Descrição: {desc}")
            comments = t.get("comments", [])
            if comments:
                lines.append(f"Comentários ({len(comments)}):")
                for c in comments:
                    date_str = c.get("created", "")[:10]
                    body = c.get("body", "")[:200]
                    lines.append(f"  [{date_str}] {c.get('author', '?')}: {body}")

    return "\n".join(lines)


def analyze_material(material_info: dict, tickets: list[dict]) -> dict:
    """Call OpenRouter to analyze a material's ticket history.

    Returns a dict with keys: resolvido, acao, justificativa, abrir_nova, confianca.
    On failure returns a fallback dict.
    """
    if not Config.OPENROUTER_API_KEY:
        return _fallback("OPENROUTER_API_KEY não configurado")

    user_prompt = _build_user_prompt(material_info, tickets)

    try:
        resp = requests.post(
            Config.OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": Config.OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"]
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

        result = json.loads(content)
        logger.info("LLM análise para %s: %s", material_info.get("codigo"), result.get("acao"))
        return result

    except requests.exceptions.Timeout:
        logger.warning("LLM timeout para %s", material_info.get("codigo"))
        return _fallback("Timeout na análise LLM")
    except requests.exceptions.HTTPError as e:
        logger.error("LLM HTTP error: %s", e)
        return _fallback(f"Erro HTTP: {e.response.status_code}")
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        logger.error("LLM resposta inválida: %s", e)
        return _fallback("Resposta LLM inválida")
    except Exception as e:
        logger.error("LLM erro inesperado: %s", e)
        return _fallback(str(e))


def _fallback(reason: str) -> dict:
    return {
        "resolvido": None,
        "acao": "Análise manual necessária",
        "justificativa": reason,
        "abrir_nova": None,
        "confianca": "baixa",
    }
