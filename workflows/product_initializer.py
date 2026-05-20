from utils.template_manager import TemplateManager


class ProductInitializer:

    @staticmethod
    def initialize_product(product_path):

        frontend_destination = f"{product_path}/frontend"
        backend_destination = f"{product_path}/backend"

        TemplateManager.copy_template(
            "templates/frontend",
            frontend_destination
        )

        TemplateManager.copy_template(
            "templates/backend",
            backend_destination
        )