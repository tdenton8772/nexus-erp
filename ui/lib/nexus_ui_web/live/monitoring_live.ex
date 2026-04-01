defmodule NexusUiWeb.MonitoringLive do
  @moduledoc """
  Live monitoring dashboard with real-time sync event log.
  Subscribes to PubSub for live event streaming from the Python backend
  (pushed via Server-Sent Events polled by a GenServer, or via a Phoenix Channel).
  """
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @refresh_interval 5_000
  @max_live_events 200

  @impl true
  def mount(_params, _session, socket) do
    if connected?(socket) do
      :timer.send_interval(@refresh_interval, self(), :refresh)
      Phoenix.PubSub.subscribe(NexusUi.PubSub, "sync_events:all")
    end

    {:ok,
     socket
     |> assign(:page_title, "Monitoring")
     |> assign(:filter_pipeline, "all")
     |> assign(:filter_status, "all")
     |> assign(:live_events, [])
     |> assign(:pipelines, [])
     |> assign(:paused, false)
     |> load_initial_data()}
  end

  @impl true
  def handle_info(:refresh, %{assigns: %{paused: true}} = socket), do: {:noreply, socket}

  def handle_info(:refresh, socket) do
    {:noreply, load_events(socket)}
  end

  def handle_info({:sync_event, event}, %{assigns: %{paused: true}} = socket) do
    {:noreply, socket}
  end

  def handle_info({:sync_event, event}, socket) do
    events = [event | socket.assigns.live_events] |> Enum.take(@max_live_events)
    {:noreply, assign(socket, :live_events, events)}
  end

  @impl true
  def handle_event("set_filter_pipeline", %{"value" => val}, socket) do
    {:noreply, socket |> assign(:filter_pipeline, val) |> load_events()}
  end

  def handle_event("set_filter_status", %{"value" => val}, socket) do
    {:noreply, socket |> assign(:filter_status, val) |> load_events()}
  end

  def handle_event("toggle_pause", _, socket) do
    {:noreply, assign(socket, :paused, !socket.assigns.paused)}
  end

  def handle_event("clear_events", _, socket) do
    {:noreply, assign(socket, :live_events, [])}
  end

  defp load_initial_data(socket) do
    pipelines =
      case ApiClient.list_pipelines() do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    socket
    |> assign(:pipelines, pipelines)
    |> load_events()
  end

  defp load_events(socket) do
    params =
      %{limit: 100, order: "desc"}
      |> maybe_add_filter(:pipeline_id, socket.assigns.filter_pipeline)
      |> maybe_add_filter(:status, socket.assigns.filter_status)

    events =
      case ApiClient.list_sync_events(params) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    assign(socket, :live_events, events)
  end

  defp maybe_add_filter(params, _key, "all"), do: params
  defp maybe_add_filter(params, key, val), do: Map.put(params, key, val)

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-4">
      <div class="flex justify-between items-center">
        <h1 class="text-2xl font-bold text-gray-900">Monitoring</h1>
        <div class="flex gap-2">
          <button phx-click="toggle_pause"
                  class={"btn-secondary text-sm " <> if @paused, do: "ring-2 ring-yellow-400", else: ""}>
            <%= if @paused, do: "▶ Resume", else: "⏸ Pause" %>
          </button>
          <button phx-click="clear_events" class="btn-secondary text-sm">Clear</button>
        </div>
      </div>

      <%!-- Filters --%>
      <div class="flex gap-3 items-center bg-white rounded-lg shadow px-4 py-3">
        <label class="text-sm text-gray-600">Pipeline:</label>
        <select phx-change="set_filter_pipeline" name="filter_pipeline"
                class="rounded border border-gray-300 px-3 py-1.5 text-sm">
          <option value="all">All Pipelines</option>
          <%= for p <- @pipelines do %>
            <option value={p["id"]} selected={@filter_pipeline == p["id"]}>
              <%= p["name"] %>
            </option>
          <% end %>
        </select>

        <label class="text-sm text-gray-600 ml-2">Status:</label>
        <select phx-change="set_filter_status" name="filter_status"
                class="rounded border border-gray-300 px-3 py-1.5 text-sm">
          <option value="all">All Statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="conflict">Conflict</option>
          <option value="skipped">Skipped</option>
        </select>

        <span class="ml-auto text-xs text-gray-400">
          <%= length(@live_events) %> events
          <%= if @paused do %>
            <span class="text-yellow-500 font-medium">(paused)</span>
          <% end %>
        </span>
      </div>

      <%!-- Event log --%>
      <div class="bg-gray-950 rounded-lg overflow-hidden font-mono text-xs">
        <div class="px-4 py-2 bg-gray-900 border-b border-gray-800 text-gray-400">
          Sync Event Log — live
        </div>
        <div class="overflow-y-auto max-h-[600px] p-2 space-y-0.5">
          <%= for event <- @live_events do %>
            <div class={"flex gap-2 px-2 py-1 rounded " <> event_bg(event["status"])}>
              <span class="text-gray-500 shrink-0 w-20"><%= format_time(event["created_at"]) %></span>
              <span class={"font-medium shrink-0 w-16 " <> event_color(event["status"])}>
                <%= String.upcase(event["status"] || "") %>
              </span>
              <span class="text-gray-300 shrink-0 w-20 capitalize"><%= event["operation"] %></span>
              <span class="text-gray-400 shrink-0 w-24 truncate"><%= event["entity_name"] %></span>
              <span class="text-gray-500 shrink-0 w-32 truncate"><%= event["record_id"] %></span>
              <span class="text-gray-600 truncate"><%= event["error_message"] %></span>
            </div>
          <% end %>
          <%= if @live_events == [] do %>
            <div class="text-gray-600 px-2 py-4 text-center">
              No events. Start a pipeline to see activity here.
            </div>
          <% end %>
        </div>
      </div>
    </div>
    """
  end

  defp event_bg("failed"), do: "bg-red-950"
  defp event_bg("conflict"), do: "bg-yellow-950"
  defp event_bg("success"), do: ""
  defp event_bg(_), do: ""

  defp event_color("failed"), do: "text-red-400"
  defp event_color("conflict"), do: "text-yellow-400"
  defp event_color("success"), do: "text-green-400"
  defp event_color("skipped"), do: "text-gray-500"
  defp event_color(_), do: "text-gray-400"

  defp format_time(nil), do: "—"
  defp format_time(ts) when is_binary(ts), do: String.slice(ts, 11, 8)
  defp format_time(_), do: "—"
end
