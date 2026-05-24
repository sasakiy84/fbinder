// Progressive enhancement for generated pages.
(() => {
  const searchPageSize = 10;
  const copyButtons = document.querySelectorAll("[data-copy-content]");

  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }

    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.inset = "0 auto auto 0";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();

    if (!copied) {
      throw new Error("copy command failed");
    }
  };

  for (const button of copyButtons) {
    button.addEventListener("click", async () => {
      const targetId = button.getAttribute("data-copy-content");
      const statusId = button.getAttribute("aria-describedby");
      const target = targetId ? document.getElementById(targetId) : null;
      const status = statusId ? document.getElementById(statusId) : null;
      const text = target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement
        ? target.value
        : target ? target.innerText : "";

      if (!text.trim()) {
        if (status) {
          status.textContent = "コピーするMarkdownがありません";
        }
        return;
      }

      try {
        await copyText(text);
        const label = button.getAttribute("data-copy-label") || "Markdownをコピー";
        button.textContent = "コピー済み";
        if (status) {
          status.textContent = "Markdownをコピーしました";
        }
        window.setTimeout(() => {
          button.textContent = label;
          if (status) {
            status.textContent = "";
          }
        }, 1800);
      } catch {
        if (status) {
          status.textContent = "コピーできませんでした";
        }
      }
    });
  }

  const searchRoot = document.querySelector("[data-search-index]");
  if (!(searchRoot instanceof HTMLElement)) {
    return;
  }

  const searchForm = searchRoot.querySelector(".site-search-form");
  const searchInput = searchRoot.querySelector("#site-search-input");
  const searchStatus = searchRoot.querySelector("#site-search-status");
  const searchResults = searchRoot.querySelector("#site-search-results");
  const searchPagination = searchRoot.querySelector("#site-search-pagination");
  const searchIndexHref = searchRoot.getAttribute("data-search-index");

  if (
    !(searchForm instanceof HTMLFormElement)
    || !(searchInput instanceof HTMLInputElement)
    || !(searchStatus instanceof HTMLElement)
    || !(searchResults instanceof HTMLUListElement)
    || !(searchPagination instanceof HTMLElement)
    || !searchIndexHref
  ) {
    return;
  }

  const searchIndexUrl = new URL(searchIndexHref, window.location.href);
  const searchBaseUrl = new URL(".", searchIndexUrl);
  let searchIndexPromise = null;
  let searchInputTimer = 0;

  const normalizeSearchText = (value) => value.normalize("NFKC").toLowerCase();

  const parseSearchState = () => {
    const params = new URLSearchParams(window.location.search);
    const query = params.get("q") || "";
    const pageText = params.get("page") || "1";
    const pageNumber = Number.parseInt(pageText, 10);
    return {
      query,
      page: Number.isFinite(pageNumber) && pageNumber > 0 ? pageNumber : 1,
    };
  };

  const urlForSearchState = (state) => {
    const url = new URL(window.location.href);
    url.hash = "";
    if (state.query.trim()) {
      url.searchParams.set("q", state.query);
      url.searchParams.set("page", String(state.page));
    } else {
      url.searchParams.delete("q");
      url.searchParams.delete("page");
    }
    return url;
  };

  const writeSearchState = (state, mode) => {
    const nextUrl = urlForSearchState(state);
    if (nextUrl.href === window.location.href) {
      return;
    }
    if (mode === "push") {
      window.history.pushState(null, "", nextUrl);
      return;
    }
    window.history.replaceState(null, "", nextUrl);
  };

  const loadSearchIndex = async () => {
    if (searchIndexPromise) {
      return searchIndexPromise;
    }
    searchIndexPromise = fetch(searchIndexUrl)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`search index request failed: ${response.status}`);
        }
        return response.json();
      })
      .then((data) => data && Array.isArray(data.items) ? data.items : []);
    return searchIndexPromise;
  };

  const clearSearchResults = () => {
    searchStatus.textContent = "";
    searchResults.replaceChildren();
    searchPagination.replaceChildren();
  };

  const resultUrl = (item) => new URL(item.url || "", searchBaseUrl).href;

  const termsForQuery = (query) => normalizeSearchText(query).split(/\s+/).filter(Boolean);

  const searchItems = (items, terms) => {
    const matches = [];
    for (const item of items) {
      const title = typeof item.title === "string" ? item.title : "";
      const text = typeof item.text === "string" ? item.text : "";
      const haystack = normalizeSearchText(`${title} ${text}`);
      if (terms.every((term) => haystack.includes(term))) {
        matches.push(item);
      }
    }
    return matches;
  };

  const appendHighlightedText = (parent, text, term) => {
    const normalizedText = normalizeSearchText(text);
    const index = normalizedText.indexOf(term);
    if (index < 0) {
      parent.append(document.createTextNode(text));
      return;
    }

    parent.append(document.createTextNode(text.slice(0, index)));
    const mark = document.createElement("mark");
    mark.textContent = text.slice(index, index + term.length);
    parent.append(mark);
    parent.append(document.createTextNode(text.slice(index + term.length)));
  };

  const snippetForItem = (item, terms) => {
    const text = typeof item.text === "string" ? item.text : "";
    const normalizedText = normalizeSearchText(text);
    const matchIndex = terms.reduce((found, term) => {
      const index = normalizedText.indexOf(term);
      if (index < 0) {
        return found;
      }
      return found < 0 ? index : Math.min(found, index);
    }, -1);
    if (matchIndex < 0) {
      return text.slice(0, 140);
    }
    const start = Math.max(0, matchIndex - 48);
    const end = Math.min(text.length, matchIndex + 92);
    const prefix = start > 0 ? "..." : "";
    const suffix = end < text.length ? "..." : "";
    return `${prefix}${text.slice(start, end)}${suffix}`;
  };

  const renderResults = (matches, terms, page) => {
    searchResults.replaceChildren();
    const totalPages = Math.max(1, Math.ceil(matches.length / searchPageSize));
    const start = (page - 1) * searchPageSize;
    const pageItems = matches.slice(start, start + searchPageSize);

    for (const item of pageItems) {
      const li = document.createElement("li");
      li.className = "search-result";

      const link = document.createElement("a");
      link.href = resultUrl(item);
      link.textContent = typeof item.title === "string" && item.title ? item.title : "Untitled";
      li.append(link);

      const meta = document.createElement("p");
      meta.className = "search-result-meta";
      const kind = typeof item.kind === "string" ? item.kind : "page";
      const updated = typeof item.updated === "string" ? item.updated : "";
      meta.textContent = updated ? `${kind} / ${updated}` : kind;
      li.append(meta);

      const snippet = document.createElement("p");
      snippet.className = "search-snippet";
      appendHighlightedText(snippet, snippetForItem(item, terms), terms[0] || "");
      li.append(snippet);

      searchResults.append(li);
    }

    renderPagination(page, totalPages);
  };

  const renderPagination = (page, totalPages) => {
    searchPagination.replaceChildren();
    if (totalPages <= 1) {
      return;
    }

    const currentState = parseSearchState();
    const previous = document.createElement("a");
    previous.textContent = "前へ";
    previous.href = urlForSearchState({query: currentState.query, page: Math.max(1, page - 1)}).href;
    if (page === 1) {
      previous.setAttribute("aria-disabled", "true");
    }
    searchPagination.append(previous);

    const status = document.createElement("span");
    status.textContent = `${page} / ${totalPages}`;
    searchPagination.append(status);

    const next = document.createElement("a");
    next.textContent = "次へ";
    next.href = urlForSearchState({query: currentState.query, page: Math.min(totalPages, page + 1)}).href;
    if (page === totalPages) {
      next.setAttribute("aria-disabled", "true");
    }
    searchPagination.append(next);
  };

  const renderSearchFromUrl = async () => {
    const state = parseSearchState();
    searchInput.value = state.query;

    if (!state.query.trim()) {
      clearSearchResults();
      return;
    }

    try {
      const items = await loadSearchIndex();
      const terms = termsForQuery(state.query);
      const matches = searchItems(items, terms);
      const totalPages = Math.max(1, Math.ceil(matches.length / searchPageSize));
      const page = Math.min(state.page, totalPages);
      if (page !== state.page) {
        writeSearchState({query: state.query, page}, "replace");
      }

      searchStatus.textContent = matches.length === 0
        ? "該当するページはありません"
        : `${matches.length} 件中 ${((page - 1) * searchPageSize) + 1}-${Math.min(page * searchPageSize, matches.length)} 件を表示`;
      renderResults(matches, terms, page);
    } catch {
      searchStatus.textContent = "検索インデックスを読み込めませんでした";
      searchResults.replaceChildren();
      searchPagination.replaceChildren();
    }
  };

  searchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    writeSearchState({query: searchInput.value.trim(), page: 1}, "push");
    renderSearchFromUrl();
  });

  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchInputTimer);
    searchInputTimer = window.setTimeout(() => {
      writeSearchState({query: searchInput.value.trim(), page: 1}, "replace");
      renderSearchFromUrl();
    }, 220);
  });

  searchPagination.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLAnchorElement) || target.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    window.history.pushState(null, "", target.href);
    renderSearchFromUrl();
  });

  window.addEventListener("popstate", () => {
    renderSearchFromUrl();
  });

  renderSearchFromUrl();
})();
