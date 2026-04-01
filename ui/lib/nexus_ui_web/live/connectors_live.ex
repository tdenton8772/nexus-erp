defmodule NexusUiWeb.ConnectorsLive do
  use NexusUiWeb, :live_view

  alias NexusUi.ApiClient

  @impl true
  def mount(_params, _session, socket) do
    {:ok,
     socket
     |> assign(:page_title, "Connectors")
     |> assign(:connector_types, [])
     |> assign(:show_modal, false)
     |> assign(:form, %{})
     |> assign(:testing_id, nil)
     |> assign(:test_results, %{})
     |> load_connectors()}
  end

  @impl true
  def handle_params(params, _url, socket) do
    {:noreply, apply_action(socket, socket.assigns.live_action, params)}
  end

  defp apply_action(socket, :index, _), do: socket

  defp apply_action(socket, :new, _) do
    types =
      case ApiClient.list_connector_types() do
        {:ok, data} -> data
        _ -> []
      end

    socket
    |> assign(:connector_types, types)
    |> assign(:show_modal, true)
    |> assign(:form, %{
      "system_name" => "",
      "display_name" => "",
      "base_url" => "",
      "credentials" => "{}"
    })
  end

  defp apply_action(socket, :show, %{"id" => id}) do
    case ApiClient.get_connector(id) do
      {:ok, connector} -> assign(socket, :selected_connector, connector)
      _ -> socket
    end
  end

  @impl true
  def handle_event("close_modal", _, socket) do
    {:noreply, push_patch(socket, to: "/connectors")}
  end

  def handle_event("save_connector", %{"connector" => params}, socket) do
    case ApiClient.create_connector(params) do
      {:ok, _} ->
        {:noreply,
         socket
         |> put_flash(:info, "Connector created")
         |> load_connectors()
         |> push_patch(to: "/connectors")}

      {:error, err} ->
        {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("test_connection", %{"id" => id}, socket) do
    socket = assign(socket, :testing_id, id)

    case ApiClient.test_connector(id) do
      {:ok, result} ->
        results = Map.put(socket.assigns.test_results, id, %{ok: result["healthy"], msg: result["message"]})
        {:noreply, socket |> assign(:testing_id, nil) |> assign(:test_results, results)}

      {:error, _} ->
        results = Map.put(socket.assigns.test_results, id, %{ok: false, msg: "Connection failed"})
        {:noreply, socket |> assign(:testing_id, nil) |> assign(:test_results, results)}
    end
  end

  def handle_event("delete_connector", %{"id" => id}, socket) do
    case ApiClient.delete_connector(id) do
      {:ok, _} -> {:noreply, socket |> put_flash(:info, "Deleted") |> load_connectors()}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  def handle_event("trigger_discovery", %{"id" => id}, socket) do
    case ApiClient.trigger_schema_discovery(id) do
      {:ok, _} -> {:noreply, put_flash(socket, :info, "Schema discovery started")}
      {:error, err} -> {:noreply, put_flash(socket, :error, inspect(err.body))}
    end
  end

  defp load_connectors(socket) do
    connectors =
      case ApiClient.list_connectors() do
        {:ok, data} -> data["items"] || data
        _ -> []
      end

    assign(socket, :connectors, connectors)
  end

  @impl true
  def render(assigns) do
    ~H"""
    <div class="p-6 space-y-4">
      <div class="flex justify-between items-center">
        <h1 class="text-2xl font-bold text-gray-900">Connectors</h1>
        <.link patch="/connectors/new" class="btn-primary">+ Add Connector</.link>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <%= for c <- @connectors do %>
          <div class="bg-white rounded-lg shadow p-4 space-y-3">
            <div class="flex justify-between items-start">
              <div>
                <h3 class="font-semibold text-gray-900"><%= c["display_name"] %></h3>
                <p class="text-xs text-gray-400 font-mono"><%= c["system_name"] %></p>
              </div>
              <span class={"px-2 py-0.5 rounded text-xs font-medium " <> status_class(c["status"])}>
                <%= c["status"] %>
              </span>
            </div>

            <p class="text-xs text-gray-500 truncate"><%= c["base_url"] %></p>

            <%!-- Test result --%>
            <%= case Map.get(@test_results, c["id"]) do %>
              <% %{ok: true, msg: msg} -> %>
                <p class="text-xs text-green-600">✓ <%= msg %></p>
              <% %{ok: false, msg: msg} -> %>
                <p class="text-xs text-red-600">✕ <%= msg %></p>
              <% _ -> %>
            <% end %>

            <div class="flex gap-2 pt-1 border-t">
              <button phx-click="test_connection" phx-value-id={c["id"]}
                      disabled={@testing_id == c["id"]}
                      class="text-xs text-blue-600 hover:underline disabled:opacity-50">
                <%= if @testing_id == c["id"], do: "Testing...", else: "Test" %>
              </button>
              <button phx-click="trigger_discovery" phx-value-id={c["id"]}
                      class="text-xs text-purple-600 hover:underline">
                Discover Schemas
              </button>
              <.link navigate={"/schemas/#{c["id"]}"} class="text-xs text-gray-600 hover:underline">
                View Schemas
              </.link>
              <button phx-click="delete_connector" phx-value-id={c["id"]}
                      data-confirm="Delete connector?"
                      class="text-xs text-red-400 hover:underline ml-auto">
                Delete
              </button>
            </div>
          </div>
        <% end %>
      </div>

      <%= if @show_modal do %>
        <.modal>
          <h2 class="text-lg font-bold mb-4">Add Connector</h2>
          <form phx-submit="save_connector" class="space-y-4">
            <div>
              <label class="text-sm font-medium text-gray-700">System Type</label>
              <select name="connector[system_name]"
                      class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm">
                <%= for t <- @connector_types do %>
                  <option value={t["system_name"]}><%= t["display_name"] %></option>
                <% end %>
              </select>
            </div>
            <.field label="Display Name" name="connector[display_name]"
                    placeholder="Sage Intacct - Production" />
            <.field label="Base URL" name="connector[base_url]"
                    placeholder="https://api.intacct.com/ia/xml/xmlgw.phtml" />
            <div>
              <label class="text-sm font-medium text-gray-700">Credentials (JSON)</label>
              <textarea name="connector[credentials]" rows="5"
                        class="mt-1 w-full rounded border border-gray-300 px-3 py-2 text-sm font-mono"
                        placeholder='{"company_id": "...", "user_id": "...", "password": "..."}'
              ></textarea>
            </div>
            <div class="flex justify-end gap-2">
              <button type="button" phx-click="close_modal" class="btn-secondary">Cancel</button>
              <button type="submit" class="btn-primary">Save Connector</button>
            </div>
          </form>
        </.modal>
      <% end %>
    </div>
    """
  end

  defp status_class("active"), do: "bg-green-100 text-green-800"
  defp status_class("error"), do: "bg-red-100 text-red-800"
  defp status_class("configuring"), do: "bg-blue-100 text-blue-800"
  defp status_class(_), do: "bg-gray-100 text-gray-700"
end
