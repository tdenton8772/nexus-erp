defmodule NexusUiWeb.CoreComponents do
  @moduledoc "Shared UI components used across all LiveViews."
  use Phoenix.Component

  # ── Modal ──────────────────────────────────────────────────────────────────

  slot :inner_block, required: true

  def modal(assigns) do
    ~H"""
    <div class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="fixed inset-0 bg-black/50" phx-click="close_modal"></div>
      <div class="relative bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6 z-10">
        <%= render_slot(@inner_block) %>
      </div>
    </div>
    """
  end

  # ── Text field ─────────────────────────────────────────────────────────────

  attr :label, :string, required: true
  attr :name, :string, required: true
  attr :value, :string, default: ""
  attr :type, :string, default: "text"
  attr :placeholder, :string, default: ""
  attr :error, :string, default: nil

  def field(assigns) do
    ~H"""
    <div>
      <label class="text-sm font-medium text-gray-700"><%= @label %></label>
      <input type={@type} name={@name} value={@value} placeholder={@placeholder}
             class={"mt-1 w-full rounded border px-3 py-2 text-sm " <>
                     if @error, do: "border-red-400 bg-red-50", else: "border-gray-300"} />
      <%= if @error do %>
        <p class="mt-0.5 text-xs text-red-600"><%= @error %></p>
      <% end %>
    </div>
    """
  end

  # ── Select field ───────────────────────────────────────────────────────────

  attr :label, :string, required: true
  attr :name, :string, required: true
  attr :options, :list, required: true   # [{label, value}]
  attr :selected, :string, default: ""
  attr :error, :string, default: nil

  def select_field(assigns) do
    ~H"""
    <div>
      <label class="text-sm font-medium text-gray-700"><%= @label %></label>
      <select name={@name}
              class={"mt-1 w-full rounded border px-3 py-2 text-sm " <>
                      if @error, do: "border-red-400", else: "border-gray-300"}>
        <option value="">— Select —</option>
        <%= for {label, value} <- @options do %>
          <option value={value} selected={@selected == value}><%= label %></option>
        <% end %>
      </select>
      <%= if @error do %>
        <p class="mt-0.5 text-xs text-red-600"><%= @error %></p>
      <% end %>
    </div>
    """
  end

  # ── Flash ──────────────────────────────────────────────────────────────────

  attr :flash, :map, required: true

  def flash_messages(assigns) do
    ~H"""
    <%= if msg = Phoenix.Flash.get(@flash, :info) do %>
      <div class="fixed top-4 right-4 z-50 bg-green-600 text-white px-4 py-3 rounded shadow-lg text-sm max-w-sm">
        <%= msg %>
      </div>
    <% end %>
    <%= if msg = Phoenix.Flash.get(@flash, :error) do %>
      <div class="fixed top-4 right-4 z-50 bg-red-600 text-white px-4 py-3 rounded shadow-lg text-sm max-w-sm">
        <%= msg %>
      </div>
    <% end %>
    """
  end
end
