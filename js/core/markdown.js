/**
 * Markdown mínimo y seguro para las respuestas del asistente.
 *
 * Primero se escapa TODO el texto y después se convierten unas pocas marcas
 * (párrafos, listas, **negrita**, *cursiva*, `código`, bloques ```...```,
 * ### títulos y enlaces http). Las citas [1], [2] se vuelven botones que abren
 * la fuente. Nunca se inserta HTML que venga del modelo.
 */

import { escapeHtml } from './dom.js';

function inline(text, validCites) {
    let t = text;
    t = t.replace(/`([^`]+)`/g, '<code>$1</code>');
    t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>');
    t = t.replace(/\bhttps?:\/\/[^\s<]+[^\s<.,;:!?)]/g,
        (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
    t = t.replace(/\[(\d{1,2})\]/g, (m, n) => (validCites.has(Number(n))
        ? `<button type="button" class="cite" data-cite="${n}" title="Ver fuente ${n}">${n}</button>`
        : m));
    return t;
}

export function renderMarkdown(source = '', citeNumbers = []) {
    const validCites = new Set(citeNumbers);
    // gpt-oss a veces cita a su manera («【2】» o «【2†L1-L4】»): se lleva a [2].
    const normal = source.replace(/\r\n/g, '\n').replace(/【(\d{1,2})(?:†[^】]*)?】/g, '[$1]');
    const escaped = escapeHtml(normal);
    const out = [];
    const blocks = escaped.split(/```/);

    blocks.forEach((block, index) => {
        if (index % 2 === 1) {
            const code = block.replace(/^[\w-]*\n/, '');
            out.push(`<pre><code>${code.replace(/\n$/, '')}</code></pre>`);
            return;
        }
        let list = null;
        let para = [];
        const flushPara = () => {
            if (para.length) out.push(`<p>${inline(para.join('<br>'), validCites)}</p>`);
            para = [];
        };
        const flushList = () => {
            if (list) out.push(`<${list.type}>${list.items.map((i) => `<li>${inline(i, validCites)}</li>`).join('')}</${list.type}>`);
            list = null;
        };
        for (const line of block.split('\n')) {
            const ul = line.match(/^\s*[-*•]\s+(.*)$/);
            const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
            const h = line.match(/^\s*#{1,6}\s+(.*)$/);
            if (ul || ol) {
                flushPara();
                const type = ul ? 'ul' : 'ol';
                if (!list || list.type !== type) { flushList(); list = { type, items: [] }; }
                list.items.push((ul || ol)[1]);
            } else if (h) {
                flushPara(); flushList();
                out.push(`<h4>${inline(h[1], validCites)}</h4>`);
            } else if (!line.trim()) {
                flushPara(); flushList();
            } else if (list && /^\s{2,}\S/.test(line)) {
                list.items[list.items.length - 1] += ' ' + line.trim();
            } else {
                flushList();
                para.push(line);
            }
        }
        flushPara();
        flushList();
    });
    return out.join('');
}
