defmodule NexusUiWeb.PipelineMonitorLive do
  @moduledoc "Real-time event log for a single pipeline."
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @refresh_interval 5_000
  @max_events 500

  @impl true
  def mount(%{"pipeline_id" => pipeline_id}, _session, socket) do
    if connected?(socket) do
      :timer.send_interval(@refresh_interval, self(), :refresh)
      Phoenix.PubSub.subscribe(NexusUi.PubSub, "sync_events:#{pipeline_id}")
    end

    {:ok,
     socket
     |> assign(:page_title, "Pipeline Monitor")
     |> assign(:pipeline_id, pipeline_id)
     |> assign(:paused, false)
     |> assign(:pipeline, %{})
     |> load_pipeline(pipeline_id)
     |> load_events(pipeline_id)}
  end

  @impl true
  def handle_info(:refresh, %{assigns: %{paused: true}} = socket), do: {:noreply, socket}

  def handle_info(:refresh, socket) do
    {:noreply, load_events(socket, socket.assigns.pipeline_id)}
  end

  def handle_info({:sync_event, event}, %{assigns: %{paused: true}} = socket) do
    {:noreply, socket}
  end

  def handle_info({:sync_event, event}, socket) do
    events = [event | socket.assigns.events] |> Enum.take(@max_events)
    {:noreply, assign(socket, :events, events)}
  end

  @impl true
  def handle_event("toggle_pause", _, socket) do
    {:noreply, assign(socket, :paused, !socket.assigns.paused)}
  end

  def handle_event("clear", _, socket) do
    {:noreply, assign(socket, :events, [])}
  end

  defp load_pipeline(socket, id) do
    pipeline =
      case ApiClient.get_pipeline(id) do
        {:ok, p} -> p
        _ -> %{}
      end

    assign(socket, :pipeline, pipeline)
  end

  defp load_events(socket, pipeline_id) do
    events =
      case ApiClient.list_sync_events(%{pipeline_id: pipeline_id, limit: 100, order: "desc"}) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    assign(socket, :events, events)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-4">
      <div class="flex items-center gap-2 text-sm text-gray-500">
        <.link navigate="/monitoring" class="hover:text-blue-600">Monitoring</.link>
        <span>›</span>
        <span class="text-gray-900 font-medium">
          <%= @pipeline["name"] || @pipeline_id %>
        </span>
      </div>

      <div class="flex justify-between items-center">
        <div>
          <h1 class="text-2xl font-bold text-gray-900">
            <%= @pipeline["name"] || "Pipeline Monitor" %>
          </h1>
          <p class="text-sm text-gray-500 mt-0.5">
            <%= @pipeline["entity_name"] %> · live event stream
          </p>
        </div>
        <div class="flex gap-2">
          <button phx-click="toggle_pause"
                  class={"btn-secondary text-sm " <> if @paused, do: "ring-2 ring-yellow-400", else: ""}>
            <%= if @paused, do: "▶ Resume", else: "⏸ Pause" %>
          </button>
          <button phx-click="clear" class="btn-secondary text-sm">Clear</button>
          <.link navigate={"/pipelines/#{@pipeline_id}"} class="btn-secondary text-sm">
            ← Pipeline Detail
          </.link>
        </div>
      </div>

      <%!-- Event log terminal --%>
      <div class="bg-gray-950 rounded-lg overflow-hidden font-mono text-xs">
        <div class="px-4 py-2 bg-gray-900 border-b border-gray-800 flex justify-between text-gray-400">
          <span>Sync Event Log — <%= @pipeline["name"] || @pipeline_id %></span>
          <span>
            <%= length(@events) %> events
            <%= if @paused do %>
              <span class="text-yellow-500 ml-1">(paused)</span>
            <% end %>
          </span>
        </div>
        <div class="overflow-y-auto max-h-[600px] p-2 space-y-0.5">
          <%= for event <- @events do %>
            <div class={"flex gap-2 px-2 py-1 rounded " <> event_bg(event["status"])}>
              <span class="text-gray-500 shrink-0 w-20">
                <%= format_time(event["created_at"]) %>
              </span>
              <span class={"font-medium shrink-0 w-16 " <> event_color(event["status"])}>
                <%= String.upcase(event["status"] || "") %>
              </span>
              <span class="text-gray-300 shrink-0 w-20 capitalize"><%= event["operation"] %></span>
              <span class="text-gray-500 shrink-0 truncate"><%= event["record_id"] %></span>
              <span class="text-red-400 truncate"><%= event["error_message"] %></span>
            </div>
          <% end %>
          <%= if @events == [] do %>
            <div class="text-gray-600 px-2 py-6 text-center">
              No events yet for this pipeline.
            </div>
          <% end %>
        </div>
      </div>
    </div>
    """
  end

  defp event_bg("failed"), do: "bg-red-950"
  defp event_bg("conflict"), do: "bg-yellow-950"
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
