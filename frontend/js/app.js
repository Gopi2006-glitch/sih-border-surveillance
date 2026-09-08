// Function to fetch telemetry and update the dashboard UI
async function updateDashboardData() {
    try {
        const response = await http://127.0.0.1:8000/api/telemetry;
        const data = await response.json();

        // Update telemetry values dynamically based on element classes or IDs
        // Tip: Add id="ai-model-val", id="tracker-val", etc. to your HTML spans for easy targeting
        console.log("Telemetry updated:", data);

        // Example: Updating camera statuses dynamically if container exists
        // You can loop through data.cameras and render online/offline status pills here.

    } catch (error) {
        console.error("Failed to sync with backend telemetry stream:", error);
    }
}

// Poll the backend every 3 seconds for real-time monitoring updates
setInterval(updateDashboardData, 3000);

// Initial fetch on page load
window.addEventListener('DOMContentLoaded', updateDashboardData);