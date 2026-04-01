defmodule NexusUiWeb.NavComponent do
  use Phoenix.Component

  attr :href, :string, required: true
  attr :label, :string, required: true
  attr :icon, :string, default: ""

  def nav_item(assigns) do
    ~H"""
    <.link
      navigate={@href}
      class="flex items-center gap-2 px-3 py-2 rounded text-sm text-gray-300 hover:bg-gray-800 hover:text-white transition-colors">
      <span class="text-base"><%= @icon %></span>
      <%= @label %>
    </.link>
    """
  end
end
