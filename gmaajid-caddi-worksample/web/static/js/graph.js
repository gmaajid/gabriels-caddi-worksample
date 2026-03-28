// CADDi Entity Resolution Graph Visualization
(function() {
    let graphData = null;
    let simulation = null;
    let selectedNode = null;

    // Tab navigation
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
            tab.classList.add('active');
            document.getElementById(tab.dataset.tab + '-view').classList.add('active');
        });
    });

    // Fetch graph data from API
    fetch('/api/graph')
        .then(r => r.json())
        .then(data => {
            graphData = data;
            renderGraph(data);
            renderTutorials(data);
            renderAlerts(data.alerts || []);
        })
        .catch(err => {
            console.error('Failed to load graph data:', err);
            document.getElementById('graph').innerHTML =
                '<text x="50%" y="50%" text-anchor="middle" fill="#ef4444">Failed to load data. Is the server running?</text>';
        });

    function renderGraph(data) {
        const svg = d3.select('#graph');
        const container = document.getElementById('graph-view');
        const width = container.clientWidth;
        const height = container.clientHeight;

        svg.attr('viewBox', [0, 0, width, height]);

        // Arrow markers for directed edges
        svg.append('defs').selectAll('marker')
            .data(['clustering', 'ma', 'division'])
            .join('marker')
            .attr('id', d => `arrow-${d}`)
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 20)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('fill', d => d === 'clustering' ? '#22c55e' : d === 'ma' ? '#f59e0b' : '#a78bfa')
            .attr('d', 'M0,-5L10,0L0,5');

        // Force simulation
        simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.edges).id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(width / 2, height / 2))
            .force('collision', d3.forceCollide().radius(30));

        // Edges
        const link = svg.append('g')
            .selectAll('line')
            .data(data.edges)
            .join('line')
            .attr('class', d => `edge ${d.type}`)
            .attr('stroke-width', d => Math.max(1, (d.combined || 0.5) * 4))
            .attr('marker-end', d => `url(#arrow-${d.type})`)
            .on('click', (event, d) => showEdgeDetail(d));

        // Nodes
        const node = svg.append('g')
            .selectAll('g')
            .data(data.nodes)
            .join('g')
            .attr('class', d => `node ${d.type}`)
            .call(d3.drag()
                .on('start', dragStarted)
                .on('drag', dragged)
                .on('end', dragEnded));

        node.append('circle')
            .attr('r', d => d.type === 'canonical' ? 14 : d.type === 'division' ? 10 : 8)
            .on('click', (event, d) => {
                event.stopPropagation();
                selectNode(d, data, node, link);
            });

        node.append('text')
            .attr('dx', 18)
            .attr('dy', 4)
            .text(d => d.id.length > 25 ? d.id.slice(0, 22) + '...' : d.id);

        // Tooltip on hover
        node.append('title')
            .text(d => `${d.id} (${d.type}, ${d.count || 0} occurrences)`);

        simulation.on('tick', () => {
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${d.x},${d.y})`);
        });

        // Click background to deselect
        svg.on('click', () => {
            selectedNode = null;
            node.classed('highlighted', false);
            link.classed('highlighted', false);
            document.getElementById('detail-content').innerHTML = '<em>Click a node or edge</em>';
        });

        // Search
        document.getElementById('search').addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            node.classed('highlighted', d => query && d.id.toLowerCase().includes(query));
        });

        // Source filter
        document.getElementById('source-filter').addEventListener('change', (e) => {
            const filter = e.target.value;
            link.attr('display', d => {
                if (filter === 'all') return 'block';
                return d.type === filter || d.source_type === filter ? 'block' : 'none';
            });
        });
    }

    function selectNode(d, data, nodeSelection, linkSelection) {
        selectedNode = d;
        // Highlight connected edges and nodes
        const connectedEdges = data.edges.filter(e =>
            (e.source.id || e.source) === d.id || (e.target.id || e.target) === d.id
        );
        const connectedIds = new Set([d.id]);
        connectedEdges.forEach(e => {
            connectedIds.add(e.source.id || e.source);
            connectedIds.add(e.target.id || e.target);
        });

        nodeSelection.classed('highlighted', n => connectedIds.has(n.id));
        linkSelection.classed('highlighted', e =>
            (e.source.id || e.source) === d.id || (e.target.id || e.target) === d.id
        );

        // Show details
        let html = `<div><strong>${d.id}</strong></div>`;
        html += `<div><span class="label">Type:</span> ${d.type}</div>`;
        html += `<div><span class="label">Occurrences:</span> ${d.count || 0}</div>`;

        const edges = connectedEdges.map(e => {
            const other = (e.source.id || e.source) === d.id ? (e.target.id || e.target) : (e.source.id || e.source);
            return `<div style="margin-top:4px; padding:4px 0; border-top:1px solid #334155">
                <span class="label">${e.type}:</span> ${other}<br>
                <span class="score">J=${(e.jaccard||0).toFixed(2)} E=${(e.embedding||0).toFixed(2)} C=${(e.combined||0).toFixed(2)}</span>
                ${e.event_id ? `<br><span class="label">Event:</span> ${e.event_id} (${e.event_date || ''})` : ''}
            </div>`;
        });
        html += edges.join('');
        document.getElementById('detail-content').innerHTML = html;
    }

    function showEdgeDetail(d) {
        let html = `<div><strong>${d.type} edge</strong></div>`;
        html += `<div><span class="label">From:</span> ${d.source.id || d.source}</div>`;
        html += `<div><span class="label">To:</span> ${d.target.id || d.target}</div>`;
        html += `<div><span class="label">Confidence:</span> <span class="score">${(d.combined||0).toFixed(3)}</span></div>`;
        if (d.jaccard !== undefined) html += `<div><span class="label">Jaccard:</span> <span class="score">${d.jaccard.toFixed(3)}</span></div>`;
        if (d.embedding !== undefined) html += `<div><span class="label">Embedding:</span> <span class="score">${d.embedding.toFixed(3)}</span></div>`;
        if (d.event_id) html += `<div><span class="label">M&A Event:</span> ${d.event_id}</div>`;
        if (d.event_date) html += `<div><span class="label">Event Date:</span> ${d.event_date}</div>`;
        document.getElementById('detail-content').innerHTML = html;
    }

    function renderTutorials(data) {
        const tutorials = [
            {
                tier: 1, title: "Tutorial 1: Resolving Abbreviations",
                desc: "See how 'APEX MFG' automatically maps to 'Apex Manufacturing' using token-level Jaccard similarity with abbreviation expansion.",
                steps: [
                    "1. In the Graph tab, search for 'APEX MFG'",
                    "2. Click the highlighted node — notice the clustering edge to 'Apex Manufacturing'",
                    "3. The edge shows J=1.00 (perfect Jaccard after 'mfg' expands to 'manufacturing')",
                    "4. This is a Tier 1 (Easy) resolution — no M&A registry needed"
                ]
            },
            {
                tier: 2, title: "Tutorial 2: Handling Typos",
                desc: "Watch the system resolve 'Quik-Fab Industries' to 'QuickFab Industries' despite the misspelling.",
                steps: [
                    "1. Search for 'Quik-Fab' in the graph",
                    "2. The embedding similarity catches this even though Jaccard is low",
                    "3. Combined confidence is moderate — this is Tier 2 (Medium)",
                    "4. Run: caddi-cli demo run — see Tier 2 results in the benchmark table"
                ]
            },
            {
                tier: 3, title: "Tutorial 3: Post-Acquisition Name",
                desc: "When Apex acquired QuickFab, orders started appearing as 'Apex-QuickFab Industries'. The clustering can't resolve this — but the M&A registry can.",
                steps: [
                    "1. Search for 'Apex-QuickFab' — notice the dashed M&A edge",
                    "2. Click the edge — it shows the acquisition event and date (2024-07-15)",
                    "3. The resolver traced: Apex-QuickFab → MA event → Apex Manufacturing",
                    "4. This is Tier 3 (Hard) — requires the M&A registry",
                    "5. Try: caddi-cli ma show <event-id> to see the full event details"
                ]
            },
            {
                tier: 4, title: "Tutorial 4: Complete Rebrand (Zero Overlap)",
                desc: "'Zenith Thermal Solutions' has ZERO token overlap with 'Precision Thermal Co'. No AI clustering can solve this. Only the M&A registry knows they're the same company.",
                steps: [
                    "1. Search for 'Zenith Thermal' — dashed edge to 'Precision Thermal Co'",
                    "2. The clustering scores are near zero (J=0.00, E=0.15)",
                    "3. Resolution came entirely from the M&A registry (rebrand event)",
                    "4. This is Tier 4 (Adversarial) — impossible without corporate event data",
                    "5. Try removing the event: caddi-cli ma remove <event-id>",
                    "6. Re-run: caddi-cli demo run — watch Tier 4 recall drop to 0%"
                ]
            },
            {
                tier: 0, title: "Tutorial 5: Detecting Broken Chains",
                desc: "What happens when M&A data is incomplete? The system detects gaps and alerts you.",
                steps: [
                    "1. Run: caddi-cli ma validate — currently shows 'No issues found'",
                    "2. Remove the QuickFab acquisition: caddi-cli ma remove <acquisition-event-id>",
                    "3. Re-run: caddi-cli demo run — 'AQF Holdings' becomes unresolved",
                    "4. The system flags this as a broken chain in the Alerts tab",
                    "5. Add the event back: caddi-cli ma add --type acquisition ...",
                    "6. Re-run: resolution restored, alert cleared"
                ]
            },
            {
                tier: 0, title: "Tutorial 6: Divisions vs Acquisitions",
                desc: "Bright Star Foundrys is a division of Apex — it keeps its own identity for POs but the parent relationship is tracked.",
                steps: [
                    "1. Search for 'Bright Star' — purple node with thin solid edge to Apex",
                    "2. This is a division edge (not M&A) — Bright Star keeps its own canonical name",
                    "3. POs from 'Bright Star Foundrys' resolve to 'Bright Star Foundrys', NOT 'Apex'",
                    "4. But analytics can aggregate: total Apex family spend includes all divisions",
                    "5. Run: caddi-cli mappings --all — see divisions listed under their parent"
                ]
            }
        ];

        const container = document.getElementById('tutorial-list');
        container.innerHTML = '<h2 style="margin-bottom:16px">Guided Tutorials</h2><p style="color:#94a3b8;margin-bottom:24px">Step-by-step walkthroughs demonstrating entity resolution capabilities, from simple abbreviations to adversarial rebrands.</p>';

        tutorials.forEach(t => {
            const tierClass = t.tier > 0 ? `tier-${t.tier}` : '';
            const tierLabel = t.tier > 0 ? `Tier ${t.tier}` : 'Advanced';
            const card = document.createElement('div');
            card.className = 'tutorial-card';
            card.innerHTML = `
                <span class="tier ${tierClass}">${tierLabel}</span>
                <h4>${t.title}</h4>
                <p>${t.desc}</p>
                <div class="tutorial-steps" style="display:none; margin-top:12px; padding-top:12px; border-top:1px solid #334155">
                    ${t.steps.map(s => `<div style="padding:4px 0; color:#cbd5e1; font-size:13px">${s}</div>`).join('')}
                </div>
            `;
            card.addEventListener('click', () => {
                const steps = card.querySelector('.tutorial-steps');
                steps.style.display = steps.style.display === 'none' ? 'block' : 'none';
            });
            container.appendChild(card);
        });
    }

    function renderAlerts(alerts) {
        const container = document.getElementById('alerts-list');
        if (!alerts.length) {
            container.innerHTML = '<div style="padding:24px;color:#94a3b8"><h2 style="margin-bottom:8px">Alerts</h2><p>No validation issues found. The M&A registry is healthy.</p></div>';
            return;
        }
        container.innerHTML = '<h2 style="padding:0 0 16px">Alerts</h2>';
        alerts.forEach(a => {
            const card = document.createElement('div');
            card.className = `alert-card ${a.severity}`;
            card.innerHTML = `
                <div class="alert-type">${a.severity}: ${a.type}</div>
                <div class="alert-message">${a.message}</div>
                <div class="alert-action">Action: ${a.action}</div>
            `;
            container.appendChild(card);
        });
    }

    function dragStarted(event, d) {
        if (!event.active) simulation.alphaTarget(0.3).restart();
        d.fx = d.x; d.fy = d.y;
    }

    function dragged(event, d) { d.fx = event.x; d.fy = event.y; }

    function dragEnded(event, d) {
        if (!event.active) simulation.alphaTarget(0);
        d.fx = null; d.fy = null;
    }
})();
