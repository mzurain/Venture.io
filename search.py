from config import search_client


def run_query_batch(queries: list[str], depth: str = "basic") -> tuple[str, list]:
    context_parts = []
    raw_results   = []

    for query in queries:
        try:
            result = search_client.search(
                query=query,
                search_depth=depth,
                max_results=5,
                include_answer=True,
                include_raw_content=True,
            )

            if result.get("answer"):
                context_parts.append(f"[Search: {query}]\n{result['answer']}")

            for r in result.get("results", []):
                text = (r.get("raw_content") or r.get("content") or "")[:1200]
                if text:
                    context_parts.append(f"Source: {r.get('url', '')}\n{text}")
                raw_results.append(r)

        except Exception as e:
            context_parts.append(f"[Search failed: {query} — {str(e)}]")

    return "\n\n---\n\n".join(context_parts), raw_results
