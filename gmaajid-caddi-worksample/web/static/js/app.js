// CADDi Entity Resolution — Web Application
(function() {
    'use strict';

    // ========== WebSocket ==========
    let ws = null;
    const handlers = { terminal: [], graph: [], tutorial: [] };

    function wsConnect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${location.host}/ws`);
        ws.onopen = () => updateStatus('connected');
        ws.onclose = () => { updateStatus('disconnected'); setTimeout(wsConnect, 3000); };
        ws.onerror = () => updateStatus('error');
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            (handlers[msg.channel] || []).forEach(h => h(msg.type, msg.data));
        };
    }

    function wsSend(channel, type, data) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ channel, type, data: data || {} }));
        }
    }

    function onMessage(channel, handler) {
        handlers[channel] = handlers[channel] || [];
        handlers[channel].push(handler);
    }

    function updateStatus(status) {
        const el = document.getElementById('status-text');
        if (el) el.textContent = status;
    }

    // ========== Tab Navigation ==========
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab + '-view').classList.add('active');
        });
    });

    // ========== Terminal (xterm.js) ==========
    let term = null;

    function initTerminal() {
        if (typeof Terminal === 'undefined') {
            console.warn('xterm.js not loaded');
            return;
        }
        term = new Terminal({
            cursorBlink: true,
            fontSize: 13,
            fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
            theme: {
                background: '#0f172a',
                foreground: '#e2e8f0',
                cursor: '#38bdf8',
                selectionBackground: '#334155',
            },
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(document.getElementById('terminal'));
        fitAddon.fit();

        term.onData(data => wsSend('terminal', 'terminal-input', { data }));
        term.onResize(({ cols, rows }) => wsSend('terminal', 'terminal-resize', { cols, rows }));

        onMessage('terminal', (type, data) => {
            if (type === 'terminal-output') term.write(data.data);
        });

        // Resize on window resize and drag handle
        const observer = new ResizeObserver(() => fitAddon.fit());
        observer.observe(document.getElementById('terminal-panel'));
    }

    // ========== Resize Handle ==========
    (function() {
        const handle = document.getElementById('resize-handle');
        const termPanel = document.getElementById('terminal-panel');
        let startY, startH;

        handle.addEventListener('mousedown', (e) => {
            startY = e.clientY;
            startH = termPanel.offsetHeight;
            document.addEventListener('mousemove', onDrag);
            document.addEventListener('mouseup', onStop);
            e.preventDefault();
        });

        function onDrag(e) {
            const delta = startY - e.clientY;
            termPanel.style.height = Math.max(100, startH + delta) + 'px';
        }

        function onStop() {
            document.removeEventListener('mousemove', onDrag);
            document.removeEventListener('mouseup', onStop);
        }
    })();

    // ========== Graph (D3.js) ==========
    let graphData = null;
    let simulation = null;
    let showWeights = localStorage.getItem('showWeights') === 'true';

    document.getElementById('show-weights').checked = showWeights;
    document.getElementById('show-weights').addEventListener('change', (e) => {
        showWeights = e.target.checked;
        localStorage.setItem('showWeights', showWeights);
        document.querySelectorAll('.edge-label').forEach(el => {
            el.classList.toggle('hidden', !showWeights);
        });
    });

    function initGraph(data) {
        graphData = data;
        const svg = d3.select('#graph');
        svg.selectAll('*').remove();

        const container = document.getElementById('graph-view');
        const width = container.clientWidth;
        const height = container.clientHeight;
        svg.attr('viewBox', [0, 0, width, height]);

        // Arrow markers
        const defs = svg.append('defs');
        [['clustering', '#22c55e'], ['ma', '#f59e0b'], ['division', '#a78bfa']].forEach(([type, color]) => {
            defs.append('marker').attr('id', `arrow-${type}`).attr('viewBox', '0 -5 10 10')
                .attr('refX', 20).attr('refY', 0).attr('markerWidth', 6).attr('markerHeight', 6)
                .attr('orient', 'auto').append('path').attr('fill', color).attr('d', 'M0,-5L10,0L0,5');
        });

        const g = svg.append('g');

        // Zoom
        svg.call(d3.zoom().scaleExtent([0.2, 5]).on('zoom', (e) => g.attr('transform', e.transform)));

        // Edges
        const link = g.append('g').selectAll('line').data(data.edges).join('line')
            .attr('class', d => `edge ${d.type}`)
            .attr('stroke-width', d => Math.max(1, (d.combined || 0.5) * 3))
            .attr('marker-end', d => `url(#arrow-${d.type})`)
            .on('click', (e, d) => showEdgeDetail(d));

        // Edge labels
        const edgeLabels = g.append('g').selectAll('text').data(data.edges).join('text')
            .attr('class', `edge-label ${showWeights ? '' : 'hidden'}`)
            .text(d => {
                if (d.type === 'ma') return `M&A ${d.event_date || ''}`;
                if (d.type === 'division') return 'div';
                return `C=${(d.combined||0).toFixed(2)}`;
            });

        // Nodes
        const node = g.append('g').selectAll('g').data(data.nodes).join('g')
            .attr('class', d => `node ${d.type}`)
            .call(d3.drag().on('start', dragStart).on('drag', dragged).on('end', dragEnd));

        node.append('circle')
            .attr('r', d => d.type === 'canonical' ? 12 : d.type === 'division' ? 9 : 7)
            .on('click', (e, d) => { e.stopPropagation(); selectNode(d, data, node, link); });

        node.append('text').attr('dx', 15).attr('dy', 4)
            .text(d => d.id.length > 25 ? d.id.slice(0, 22) + '...' : d.id);

        node.append('title').text(d => `${d.id} (${d.type}, ${d.count||0}x)`);

        // Force simulation
        simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.edges).id(d => d.id).distance(90))
            .force('charge', d3.forceManyBody().strength(-250))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(25));

        simulation.on('tick', () => {
            link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
            edgeLabels.attr('x', d => (d.source.x + d.target.x) / 2)
                      .attr('y', d => (d.source.y + d.target.y) / 2);
            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        svg.on('click', () => clearHighlights(node, link));
        updateGraphStatus(data);

        // Search
        document.getElementById('search').addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            node.classed('highlighted', d => q && d.id.toLowerCase().includes(q));
        });

        // Source filter
        document.getElementById('source-filter').addEventListener('change', (e) => {
            const f = e.target.value;
            link.attr('display', d => f === 'all' || d.type === f || d.source_type === f ? 'block' : 'none');
        });
    }

    function selectNode(d, data, nodeSelection, linkSelection) {
        const connected = new Set([d.id]);
        data.edges.forEach(e => {
            const sid = e.source.id || e.source;
            const tid = e.target.id || e.target;
            if (sid === d.id || tid === d.id) { connected.add(sid); connected.add(tid); }
        });
        nodeSelection.classed('highlighted', n => connected.has(n.id));
        linkSelection.classed('highlighted', e => (e.source.id||e.source) === d.id || (e.target.id||e.target) === d.id);

        let html = `<div><strong>${d.id}</strong></div><div>Type: ${d.type}</div><div>Count: ${d.count||0}</div>`;
        data.edges.filter(e => (e.source.id||e.source) === d.id || (e.target.id||e.target) === d.id).forEach(e => {
            const other = (e.source.id||e.source) === d.id ? (e.target.id||e.target) : (e.source.id||e.source);
            html += `<div style="margin-top:4px;padding-top:4px;border-top:1px solid #334155">${e.type}: ${other}<br><span style="font-family:monospace;font-size:11px">J=${(e.jaccard||0).toFixed(2)} E=${(e.embedding||0).toFixed(2)} C=${(e.combined||0).toFixed(2)}</span>`;
            if (e.event_id) html += `<br>Event: ${e.event_id} (${e.event_date||''})`;
            html += '</div>';
        });
        document.getElementById('detail-content').innerHTML = html;
    }

    function showEdgeDetail(d) {
        let html = `<div><strong>${d.type} edge</strong></div>`;
        html += `<div>From: ${d.source.id||d.source}</div><div>To: ${d.target.id||d.target}</div>`;
        html += `<div style="font-family:monospace">C=${(d.combined||0).toFixed(3)}`;
        if (d.jaccard !== undefined) html += ` J=${d.jaccard.toFixed(3)} E=${d.embedding.toFixed(3)}`;
        html += '</div>';
        if (d.event_id) html += `<div>Event: ${d.event_id}</div>`;
        document.getElementById('detail-content').innerHTML = html;
    }

    function clearHighlights(nodeSelection, linkSelection) {
        nodeSelection.classed('highlighted', false).classed('trace-start', false).classed('trace-resolved', false);
        linkSelection.classed('highlighted', false).classed('trace-active', false);
        document.getElementById('detail-content').innerHTML = '<em>Click a node or edge</em>';
    }

    function updateGraphStatus(data) {
        document.getElementById('status-graph').textContent = `${data.nodes.length} nodes, ${data.edges.length} edges`;
    }

    // Graph highlights for tutorials
    function highlightNodes(nodeIds) {
        d3.selectAll('.node').classed('highlighted', d => nodeIds.includes(d.id));
    }

    function zoomToNode(nodeId) {
        const node = graphData?.nodes?.find(n => n.id === nodeId);
        if (!node || !node.x) return;
        const svg = d3.select('#graph');
        const container = document.getElementById('graph-view');
        const w = container.clientWidth, h = container.clientHeight;
        svg.transition().duration(750).call(
            d3.zoom().transform,
            d3.zoomIdentity.translate(w/2 - node.x, h/2 - node.y)
        );
    }

    // Chain traversal animation
    function playTrace(chain) {
        if (!chain || !chain.length) return;
        const allNodes = d3.selectAll('.node');
        const allEdges = d3.selectAll('.edge');

        chain.forEach((step, i) => {
            setTimeout(() => {
                if (step.node) {
                    const action = step.action || 'start';
                    allNodes.filter(d => d.id === step.node)
                        .classed('trace-start', action === 'start')
                        .classed('trace-resolved', action === 'resolved');
                    if (action === 'start' || action === 'resolved') zoomToNode(step.node);
                }
                if (step.edge) {
                    allEdges.filter(d => {
                        const s = d.source.id || d.source;
                        const t = d.target.id || d.target;
                        return step.edge.includes(s) && step.edge.includes(t);
                    }).classed('trace-active', true);
                }
            }, step.delay_ms || i * 800);
        });

        // Clear after animation
        const totalDelay = Math.max(...chain.map(s => s.delay_ms || 0)) + 3000;
        setTimeout(() => {
            allNodes.classed('trace-start', false).classed('trace-resolved', false);
            allEdges.classed('trace-active', false);
        }, totalDelay);
    }

    // Graph update with diff animation
    function updateGraph(newData) {
        const diff = newData.diff;
        if (diff && (diff.added_nodes.length || diff.removed_nodes.length)) {
            showDiffBanner(diff);
        }
        initGraph(newData);  // Full re-render for now; incremental later
    }

    function showDiffBanner(diff) {
        const banner = document.getElementById('diff-banner');
        const parts = [];
        if (diff.added_nodes.length) parts.push(`+${diff.added_nodes.length} nodes`);
        if (diff.removed_nodes.length) parts.push(`-${diff.removed_nodes.length} nodes`);
        if (diff.added_edges.length) parts.push(`+${diff.added_edges.length} edges`);
        if (diff.removed_edges.length) parts.push(`-${diff.removed_edges.length} edges`);
        if (!parts.length) return;
        banner.textContent = parts.join(', ');
        banner.style.display = 'block';
        setTimeout(() => { banner.style.display = 'none'; }, 3000);
    }

    function dragStart(event, d) { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }
    function dragged(event, d) { d.fx = event.x; d.fy = event.y; }
    function dragEnd(event, d) { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }

    // ========== Tutorials ==========
    let currentTutorialMode = 'animated';

    function initTutorials() {
        fetch('/api/tutorials').then(r => r.json()).then(tutorials => {
            const list = document.getElementById('tutorial-list');
            list.innerHTML = '<h2>Guided Tutorials</h2><p style="color:#94a3b8;margin-bottom:20px">Step-by-step walkthroughs from abbreviations to adversarial rebrands.</p>';
            tutorials.forEach(t => {
                const card = document.createElement('div');
                card.className = 'tutorial-card';
                card.innerHTML = `<span class="tier tier-${t.tier}">${t.tier > 0 ? 'Tier ' + t.tier : 'Advanced'}</span><h4>${t.title}</h4><p>${t.description}</p>`;
                card.addEventListener('click', () => startTutorial(t.id));
                list.appendChild(card);
            });
        });
    }

    function startTutorial(id) {
        document.getElementById('tutorial-list').style.display = 'none';
        document.getElementById('tutorial-player').style.display = 'block';

        // Switch to graph tab to show highlights
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelector('.tab[data-tab="graph"]').classList.add('active');
        document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
        document.getElementById('graph-view').classList.add('active');

        wsSend('tutorial', 'tutorial-start', { id, mode: currentTutorialMode });
    }

    // Tutorial step display
    onMessage('tutorial', (type, data) => {
        if (type === 'tutorial-step') showTutorialStep(data);
    });

    function showTutorialStep(step) {
        document.getElementById('step-title').textContent = step.title || '';
        document.getElementById('step-narrative').textContent = step.narrative || '';

        const cmdEl = document.getElementById('step-command');
        if (step.command) {
            cmdEl.style.display = 'flex';
            document.getElementById('step-command-text').textContent = step.command;
        } else {
            cmdEl.style.display = 'none';
        }

        const noteEl = document.getElementById('step-note');
        if (step.note) {
            noteEl.style.display = 'block';
            noteEl.textContent = step.note;
        } else {
            noteEl.style.display = 'none';
        }

        // Graph interactions
        if (step.highlight_nodes && step.highlight_nodes.length) highlightNodes(step.highlight_nodes);
        if (step.zoom_to) zoomToNode(step.zoom_to);
        if (step.resolution_trace) playTrace(step.resolution_trace.chain);

        // Auto-execute command in animated mode
        if (currentTutorialMode === 'animated' && step.command && term) {
            typeCommand(step.command);
        }

        // Update progress
        // (position is tracked server-side, we'd need to fetch it)
    }

    function typeCommand(command) {
        // Typewriter effect
        let i = 0;
        const interval = setInterval(() => {
            if (i < command.length) {
                wsSend('terminal', 'terminal-input', { data: command[i] });
                i++;
            } else {
                clearInterval(interval);
                setTimeout(() => wsSend('terminal', 'terminal-input', { data: '\r' }), 200);
            }
        }, 50);
    }

    // Tutorial navigation
    document.getElementById('tutorial-next')?.addEventListener('click', () => wsSend('tutorial', 'tutorial-next'));
    document.getElementById('tutorial-prev')?.addEventListener('click', () => wsSend('tutorial', 'tutorial-prev'));
    document.getElementById('tutorial-back')?.addEventListener('click', () => {
        document.getElementById('tutorial-list').style.display = 'block';
        document.getElementById('tutorial-player').style.display = 'none';
    });
    document.getElementById('step-command-copy')?.addEventListener('click', () => {
        const cmd = document.getElementById('step-command-text').textContent;
        navigator.clipboard.writeText(cmd);
    });

    // Mode toggle
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentTutorialMode = btn.dataset.mode;
        });
    });

    // ========== Alerts ==========
    function renderAlerts(alerts) {
        const list = document.getElementById('alerts-list');
        if (!alerts || !alerts.length) {
            list.innerHTML = '<h2>Alerts</h2><p style="color:#94a3b8">No validation issues. The M&A registry is healthy.</p>';
            return;
        }
        list.innerHTML = '<h2>Alerts</h2>';
        alerts.forEach(a => {
            const card = document.createElement('div');
            card.className = `alert-card ${a.severity}`;
            card.innerHTML = `<div class="alert-type">${a.severity}: ${a.type}</div><div class="alert-message">${a.message}</div><div class="alert-action">Action: ${a.action}</div>`;
            list.appendChild(card);
        });
    }

    // ========== Graph WebSocket updates ==========
    onMessage('graph', (type, data) => {
        if (type === 'graph-updated') updateGraph(data);
    });

    // ========== Initialize ==========
    fetch('/api/graph').then(r => r.json()).then(data => {
        initGraph(data);
        renderAlerts(data.alerts || []);
    });
    initTerminal();
    initTutorials();
    wsConnect();

})();
