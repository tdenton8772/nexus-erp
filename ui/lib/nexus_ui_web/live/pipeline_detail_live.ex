defmodule NexusUiWeb.PipelineDetailLive do
  @moduledoc "Pipeline detail view — status, config, recent runs."
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @refresh_interval 10_000

  @impl true
  def mount(%{"id" => id}, _session, socket) do
    if connected?(socket) do
      :timer.send_interval(@refresh_interval, self(), :refresh)
    end

    {:ok,
     socket
     |> assign(:page_title, "Pipeline")
     |> assign(:pipeline_id, id)
     |> load_pipeline(id)
     |> load_runs(id)}
  end

  @impl true
  def handle_info(:refresh, socket) do
    {:noreply,
     socket
     |> load_pipeline(socket.assigns.pipeline_id)
     |> load_runs(socket.assigns.pipeline_id)}
  end

  @impl true
  def handle_event("start_pipeline", %{"id" => id}, socket) do
    case ApiClient.start_pipeline(id) do
      {:ok, _} ->
        {:noreply, socket |> put_flash(:info, "Pipeline started") |> load_pipeline(id)}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("pause_pipeline", %{"id" => id}, socket) do
    case ApiClient.pause_pipeline(id) do
      {:ok, _} ->
        {:noreply, socket |> put_flash(:info, "Pipeline paused") |> load_pipeline(id)}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("trigger_now", %{"id" => id}, socket) do
    case ApiClient.run_pipeline_now(id) do
      {:ok, _} ->
        {:noreply, socket |> put_flash(:info, "Sync triggered") |> load_runs(id)}
      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  defp load_pipeline(socket, id) do
    pipeline =
      case ApiClient.get_pipeline(id) do
        {:ok, p} -> p
        _ -> %{}
      end

    assign(socket, :pipeline, pipeline)
  end

  defp load_runs(socket, id) do
    runs =
      case ApiClient.list_sync_events(%{pipeline_id: id, limit: 20, order: "desc"}) do
        {:ok, data} -> data["items"] || []
        _ -> []
      end

    assign(socket, :runs, runs)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-6">
      <%!-- Breadcrumb --%>
      <div class="flex items-center gap-2 text-sm text-gray-500">
        <.link navigate="/pipelines" class="hover:text-blue-600">Pipelines</.link>
        <span>›</span>
        <span class="text-gray-900 font-medium"><%= @pipeline["name"] || @pipeline_id %></span>
      </div>

      <%!-- Header --%>
      <div class="flex justify-between items-start">
        <div>
          <h1 class="text-2xl font-bold text-gray-900"><%= @pipeline["name"] %></h1>
          <p class="text-gray-500 mt-1">
            <span class="font-mono"><%= @pipeline["entity_name"] %></span>
            · <%= String.replace(@pipeline["direction"] || "bidirectional", "_", " ") %>
            · every <%= @pipeline["poll_interval_seconds"] %>s
          </p>
        </div>
        <div class="flex gap-2">
          <%= if @pipeline["status"] == "active" do %>
            <button phx-click="pause_pipeline" phx-value-id={@pipeline_id}
                    class="btn-secondary">⏸ Pause</button>
          <% else %>
            <button phx-click="start_pipeline" phx-value-id={@pipeline_id}
                    class="btn-secondary text-green-700">▶ Start</button>
          <% end %>
          <button phx-click="trigger_now" phx-value-id={@pipeline_id}
                  class="btn-secondary">⚡ Sync Now</button>
          <.link navigate={"/pipelines/#{@pipeline_id}/mappings"} class="btn-primary">
            Edit Mappings →
          </.link>
        </div>
      </div>

      <%!-- Status cards --%>
      <div class="grid grid-cols-4 gap-4">
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-500 uppercase tracking-wider">Status</p>
          <p class={"text-lg font-bold mt-1 " <> status_text_class(@pipeline["status"])}>
            <%= @pipeline["status"] || "—" %>
          </p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-500 uppercase tracking-wider">Last Sync</p>
          <p class="text-lg font-bold mt-1 text-gray-800">
            <%= format_date(@pipeline["last_sync_at"]) %>
          </p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-500 uppercase tracking-wider">Source</p>
          <p class="text-sm font-medium mt-1 text-gray-700 truncate">
            <%= @pipeline["source_system"] || @pipeline["source_connector_id"] || "—" %>
          </p>
        </div>
        <div class="bg-white rounded-lg shadow p-4">
          <p class="text-xs text-gray-500 uppercase tracking-wider">Target</p>
          <p class="text-sm font-medium mt-1 text-gray-700 truncate">
            <%= @pipeline["target_system"] || @pipeline["target_connector_id"] || "—" %>
          </p>
        </div>
      </div>

      <%!-- Recent sync events --%>
      <div class="bg-white rounded-lg shadow overflow-hidden">
        <div class="px-4 py-3 border-b bg-gray-50 flex justify-between items-center">
          <h2 class="font-semibold text-gray-700">Recent Sync Events</h2>
          <.link navigate={"/monitoring?pipeline_id=#{@pipeline_id}"}
                 class="text-xs text-blue-600 hover:underline">
            Full log →
          </.link>
        </div>
        <table class="w-full text-sm">
          <thead class="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th class="px-4 py-2 text-left">Time</th>
              <th class="px-4 py-2 text-left">Operation</th>
              <th class="px-4 py-2 text-left">Entity</th>
              <th class="px-4 py-2 text-left">Record</th>
              <th class="px-4 py-2 text-left">Status</th>
              <th class="px-4 py-2 text-left">Error</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <%= for run <- @runs do %>
              <tr class="hover:bg-gray-50">
                <td class="px-4 py-2 text-gray-400 text-xs"><%= format_time(run["created_at"]) %></td>
                <td class="px-4 py-2 capitalize text-gray-600"><%= run["operation"] %></td>
                <td class="px-4 py-2 font-mono text-xs text-gray-700"><%= run["entity_name"] %></td>
                <td class="px-4 py-2 font-mono text-xs text-gray-500 truncate max-w-xs">
                  <%= run["record_id"] %>
                </td>
                <td class="px-4 py-2">
                  <span class={"px-2 py-0.5 rounded text-xs font-medium " <> status_class(run["status"])}>
                    <%= run["status"] %>
                  </span>
                </td>
                <td class="px-4 py-2 text-xs text-red-500 truncate max-w-xs">
                  <%= run["error_message"] %>
                </td>
              </tr>
            <% end %>
            <%= if @runs == [] do %>
              <tr>
                <td colspan="6" class="px-4 py-8 text-center text-gray-400">
                  No sync events yet. Start the pipeline or trigger a manual sync.
                </td>
              </tr>
            <% end %>
          </tbody>
        </table>
      </div>
    </div>
    """
  end

  defp status_class("success"), do: "bg-green-100 text-green-800"
  defp status_class("failed"), do: "bg-red-100 text-red-800"
  defp status_class("conflict"), do: "bg-yellow-100 text-yellow-800"
  defp status_class("skipped"), do: "bg-gray-100 text-gray-600"
  defp status_class(_), do: "bg-gray-100 text-gray-700"

  defp status_text_class("active"), do: "text-green-600"
  defp status_text_class("error"), do: "text-red-600"
  defp status_text_class("paused"), do: "text-yellow-600"
  defp status_text_class(_), do: "text-gray-600"

  defp format_date(nil), do: "—"
  defp format_date(ts) when is_binary(ts), do: String.slice(ts, 0, 16) |> String.replace("T", " ")
  defp format_date(_), do: "—"

  defp format_time(nil), do: "—"
  defp format_time(ts) when is_binary(ts), do: String.slice(ts, 11, 8)
  defp format_time(_), do: "—"
end
