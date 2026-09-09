// Point directly to the unreviewed alerts endpoint
const API_URL = "http://127.0.0.1:8001/api/alerts/unreviewed";

async function fetchAlerts() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) return;
        const alerts = await response.json();
        
        const tbody = document.getElementById("alert-tbody");
        if (!tbody) return;

        tbody.innerHTML = "";

        if (alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #64748b; padding: 16px;">No unreviewed breaches. All clear!</td></tr>`;
            return;
        }

        alerts.forEach(alert => {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>#${alert.id}</td>
                <td><span style="background: #334155; padding: 2px 6px; border-radius: 4px; font-size: 0.8rem;">${alert.camera_id}</span></td>
                <td>${alert.timestamp}</td>
                <td style="color: #f87171; font-weight: 600;">${alert.event_type}</td>
                <td>Track ID: ${alert.track_id}</td>
                <td>
                    <span class="badge-unreviewed">
                        ${alert.status}
                    </span>
                </td>
                <td>
                    <button class="btn-ack" onclick="acknowledgeAlert(${alert.id})">Acknowledge</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error("Error connecting to backend API:", err);
    }
}

async function acknowledgeAlert(id) {
    try {
        const res = await fetch(`http://127.0.0.1:8001/api/alerts/${id}/acknowledge`, {
            method: "PATCH"
        });
        if (res.ok) {
            // Immediately refresh list to drop the acknowledged item
            fetchAlerts();
        }
    } catch (err) {
        console.error("Failed to acknowledge alert:", err);
    }
}

fetchAlerts();
setInterval(fetchAlerts, 2000);