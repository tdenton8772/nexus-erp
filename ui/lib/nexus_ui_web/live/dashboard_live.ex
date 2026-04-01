defmodule NexusUiWeb.DashboardLive do
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @refresh_interval 10_000

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      :timer.send_interval(@refresh_interval, self(), :refresh)
      Phoenix.PubSub.subscribe(NexusUi.PubSub, "sync_events")
    end

    socket =
      socket
      |> assign(:page_title, "Dashboard")
      |> load_dashboard_data()

    {:ok, socket}
  end

  @impl true
  def handle_info(:refresh, socket) do
    {:noreply, load_dashboard_data(socket)}
  end

  def handle_info({:sync_event, event}, socket) do
    # Prepend the live event to the recent events list
    recent = [event | socket.assigns.recent_events] |> Enum.take(20)
    {:noreply, assign(socket, :recent_events, recent)}
  end

  @impl true
  def handle_event("run_pipeline", %{"id" => id}, socket) do
    case ApiClient.run_pipeline_now(id) do
      {:ok, _} -> {:noreply, put_flash(socket, :info, "Pipeline triggered")}
      {:error, err} -> {:noreply, put_flash(socket, :error, "Failed: #{inspect(err.body)}")}
    end
  end

  defp load_dashboard_data(socket) do
    pipelines =
      case ApiClient.list_pipelines(%{limit: 10}) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    recent_events =
      case ApiClient.list_sync_events(%{limit: 20, order: "desc"}) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    proposals =
      case ApiClient.list_proposals(%{status: "pending_review", limit: 5}) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    active_count = Enum.count(pipelines, &(&1["status"] == "active"))
    error_count = Enum.count(pipelines, &(&1["status"] == "error"))

    socket
    |> assign(:pipelines, pipelines)
    |> assign(:recent_events, recent_events)
    |> assign(:pending_proposals, proposals)
    |> assign(:active_pipeline_count, active_count)
    |> assign(:error_pipeline_count, error_count)
    |> assign(:pending_proposal_count, length(proposals))
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <h1 class="text-2xl font-bold text-gray-900">Dashboard</h1>

      <%!-- KPI Cards --%>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <.kpi_card title="Active Pipelines" value={@active_pipeline_count} color="green" />
        <.kpi_card title="Pipelines with Errors" value={@error_pipeline_count} color="red" />
        <.kpi_card title="Pending Agent Proposals" value={@pending_proposal_count} color="yellow" />
        <.kpi_card title="Total Pipelines" value={length(@pipelines)} color="blue" />
      </div>

      <%!-- Agent proposals banner --%>
      <%= if @pending_proposal_count > 0 do %>
        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 flex items-center justify-between">
          <div>
            <p class="font-medium text-yellow-800">
              <%= @pending_proposal_count %> agent proposal(s) awaiting your review
            </p>
            <p class="text-sm text-yellow-600">
              Schema mappings or healing actions need approval before applying.
            </p>
          </div>
          <.link navigate="/agent/proposals" class="btn-yellow">Review</.link>
        </div>
      <% end %>

      <%!-- Pipeline list --%>
      <div class="bg-white rounded-lg shadow">
        <div class="px-4 py-3 border-b flex justify-between items-center">
          <h2 class="font-semibold text-gray-700">Pipelines</h2>
          <.link navigate="/pipelines/new" class="btn-primary text-sm">+ New Pipeline</.link>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-4 py-2 text-left">Name</th>
              <th class="px-4 py-2 text-left">Entity</th>
              <th class="px-4 py-2 text-left">Source → Target</th>
              <th class="px-4 py-2 text-left">Status</th>
              <th class="px-4 py-2 text-left">Last Sync</th>
              <th class="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for pipeline <- @pipelines do %>
              <tr class="hover:bg-gray-50">
                <td class="px-4 py-3 font-medium">
                  <.link navigate={"/pipelines/#{pipeline["id"]}"}>
                    <%= pipeline["name"] %>
                  </.link>
                </td>
                <td class="px-4 py-3 text-gray-600"><%= pipeline["entity_name"] %></td>
                <td class="px-4 py-3 text-gray-600">
                  <%= pipeline["source_system"] %> → <%= pipeline["target_system"] %>
                </td>
                <td class="px-4 py-3"><.status_badge status={pipeline["status"]} /></td>
                <td class="px-4 py-3 text-gray-500 text-xs"><%= pipeline["last_sync_at"] || "Never" %></td>
                <td class="px-4 py-3">
                  <button phx-click="run_pipeline" phx-value-id={pipeline["id"]}
                          class="text-xs text-blue-600 hover:underline">
                    Run now
                  </button>
                </td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>

      <%!-- Recent sync events --%>
      <div class="bg-white rounded-lg shadow">
        <div class="px-4 py-3 border-b flex justify-between items-center">
          <h2 class="font-semibold text-gray-700">Recent Sync Events</h2>
          <.link navigate="/monitoring" class="text-sm text-blue-600">View all</.link>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-4 py-2 text-left">Pipeline</th>
              <th class="px-4 py-2 text-left">Entity</th>
              <th class="px-4 py-2 text-left">Operation</th>
              <th class="px-4 py-2 text-left">Status</th>
              <th class="px-4 py-2 text-left">Time</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for event <- @recent_events do %>
              <tr>
                <td class="px-4 py-2 text-gray-700"><%= event["pipeline_name"] || event["pipeline_id"] %></td>
                <td class="px-4 py-2 text-gray-600"><%= event["entity_name"] %></td>
                <td class="px-4 py-2"><span class="capitalize"><%= event["operation"] %></span></td>
                <td class="px-4 py-2"><.status_badge status={event["status"]} /></td>
                <td class="px-4 py-2 text-gray-500 text-xs"><%= event["created_at"] %></td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>
    </div>
    """
  end

  defp kpi_card(assigns) do
    ~H"""
    <div class={"bg-white rounded-lg shadow p-4 border-l-4 border-#{@color}-400"}>
      <p class="text-sm text-gray-500"><%= @title %></p>
      <p class={"text-3xl font-bold text-#{@color}-600"}><%= @value %></p>
    </div>
    """
  end

  defp status_badge(assigns) do
    color =
      case assigns.status do
        "active" -> "green"
        "success" -> "green"
        "error" -> "red"
        "failed" -> "red"
        "paused" -> "yellow"
        "draft" -> "gray"
        _ -> "gray"
      end

    assigns = assign(assigns, :color, color)

    ~H"""
    <span class={"inline-flex items-center px-2 py-0.5 rounded text-xs font-medium
                  bg-#{@color}-100 text-#{@color}-800 capitalize"}>
      <%= @status %>
    </span>
    """
  end
end
