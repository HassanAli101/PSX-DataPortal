resource "aws_s3_bucket" "uploads_bucket" {
  bucket = "psx-pdf-uploads-${random_id.suffix.hex}"
  force_destroy = true
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "aws_iam_role" "lambda_role" {
  name = "lambda_api_role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      }
    }
  ]
}
EOF
}

resource "aws_iam_policy" "lambda_policy" {
  name = "lambda_api_policy"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ],
        Effect   = "Allow",
        Resource = "${aws_s3_bucket.uploads_bucket.arn}/*"
      },
      {
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Effect   = "Allow",
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

resource "aws_lambda_function" "pdf_lambda" {
  filename         = "${path.module}/Lambda_function/lambda_function.zip"
  function_name    = "pdf_processing_lambda"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  memory_size      = 512
  timeout          = 30
  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.uploads_bucket.bucket
      NEONDB    = "postgresql://PERN_DB_owner:EYIdVCvyP3W1@ep-ancient-voice-a1cwe7oe.ap-southeast-1.aws.neon.tech/PERN_DB?sslmode=require"
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_policy_attachment]
}

resource "aws_apigatewayv2_api" "fastapi_api" {
  name          = var.api_gateway_name
  protocol_type = "HTTP"
  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    expose_headers = ["Content-Type", "Authorization"]
    max_age = 3600
  }
}

resource "aws_apigatewayv2_integration" "fastapi_integration" {
  api_id           = aws_apigatewayv2_api.fastapi_api.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.fastapi_lambda.invoke_arn
}

resource "aws_apigatewayv2_route" "fastapi_route" {
  api_id    = aws_apigatewayv2_api.fastapi_api.id
  route_key = "POST /upload"
  target    = "integrations/${aws_apigatewayv2_integration.fastapi_integration.id}"
}

resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.fastapi_lambda.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.fastapi_api.execution_arn}/*/*"
}
