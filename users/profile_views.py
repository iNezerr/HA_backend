import logging
import traceback
import os
import mimetypes
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from .permissions import ProfilePermissions, DocumentPermissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.conf import settings

# Configure logging
logger = logging.getLogger(__name__)

from .models import Document, ParsedProfile, ProjectsProfile, UserGoal, CustomUser
from .serializers import (
    DocumentSerializer, EducationProfileSerializer, ParsedProfileSerializer,
    ProfileCompletionSerializer, ProjectsProfileSerializer, UserGoalUpdateSerializer, UserGoalSerializer
)


class SecureFileUploadMixin:
    """Mixin for secure file upload handling"""

    ALLOWED_FILE_TYPES = {
        'application/pdf': '.pdf',
        'application/msword': '.doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
        'text/plain': '.txt',
        'image/jpeg': '.jpg',
        'image/png': '.png'
    }

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_FILENAME_LENGTH = 255

    def validate_file(self, uploaded_file):
        """Validate uploaded file for security"""
        try:
            # Check file size
            if uploaded_file.size > self.MAX_FILE_SIZE:
                raise ValidationError(f"File size exceeds maximum limit of {self.MAX_FILE_SIZE // (1024*1024)}MB")

            # Check filename length
            if len(uploaded_file.name) > self.MAX_FILENAME_LENGTH:
                raise ValidationError(f"Filename too long. Maximum length is {self.MAX_FILENAME_LENGTH} characters")

            # Check file extension
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            if file_extension not in self.ALLOWED_FILE_TYPES.values():
                raise ValidationError(f"File type not allowed. Allowed types: {', '.join(self.ALLOWED_FILE_TYPES.values())}")

            # Read first 2048 bytes for content validation
            file_content = uploaded_file.read(2048)
            uploaded_file.seek(0)  # Reset file pointer

            # Detect MIME type using Python's built-in mimetypes
            detected_mime, _ = mimetypes.guess_type(uploaded_file.name)
            
            # If mimetypes can't detect, fall back to extension-based check
            if not detected_mime:
                file_extension = os.path.splitext(uploaded_file.name)[1].lower()
                extension_to_mime = {v: k for k, v in self.ALLOWED_FILE_TYPES.items()}
                detected_mime = extension_to_mime.get(file_extension)

            # Validate MIME type
            if detected_mime not in self.ALLOWED_FILE_TYPES:
                raise ValidationError(f"File type not allowed. Detected: {detected_mime}")

            # Additional security checks
            if self._contains_suspicious_content(file_content):
                raise ValidationError("File contains suspicious content")

            return True

        except Exception as e:
            logger.warning(f"File validation failed for {uploaded_file.name}: {str(e)}")
            raise ValidationError(f"File validation failed: {str(e)}")

    def _contains_suspicious_content(self, file_content):
        """Check for suspicious content in file"""
        suspicious_patterns = [
            b'<script',
            b'javascript:',
            b'vbscript:',
            b'data:text/html',
            b'data:application/x-javascript'
        ]

        file_content_lower = file_content.lower()
        return any(pattern in file_content_lower for pattern in suspicious_patterns)


# Temporary endpoints for user management
@api_view(['GET'])
@permission_classes([AllowAny])  # No authentication required for temporary endpoint
def google_signups_list(request):
    """Get list of all users who signed up via Google OAuth - Temporary endpoint"""
    try:
        # Get users who have Google profile data
        users = CustomUser.objects.filter(
            profile__google_id__isnull=False
        ).select_related('profile').order_by('-date_joined')

        results = []
        for user in users:
            # Check if user is new (joined in last 24 hours)
            is_new_user = (timezone.now() - user.date_joined).days < 1

            google_data = {}
            if hasattr(user, 'profile') and user.profile:
                google_data = {
                    'name': user.profile.name or f"{user.first_name} {user.last_name}".strip(),
                    'picture': user.profile.google_picture or ''
                }

            results.append({
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'role': user.get_role(),
                'is_new_user': is_new_user,
                'created_at': user.date_joined.isoformat(),
                'google_data': google_data
            })

        return Response({
            'count': len(results),
            'results': results
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Failed to retrieve users: {str(e)}")
        return Response({
            'error': f'Failed to retrieve users: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([AllowAny])  # No authentication required for temporary endpoint
def delete_user(request, user_id):
    """Delete a specific user by ID - Temporary endpoint"""
    try:
        user = get_object_or_404(CustomUser, id=user_id)
        user_email = user.email
        user.delete()

        return Response({
            'message': f'User {user_email} deleted successfully'
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Failed to delete user: {str(e)}")
        return Response({
            'error': f'Failed to delete user: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentUploadView(SecureFileUploadMixin, APIView):
    """Upload CV/Resume documents with security validation"""
    permission_classes = [DocumentPermissions]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            # Validate uploaded file
            if 'file' not in request.FILES:
                return Response({
                    'error': 'No file provided'
                }, status=status.HTTP_400_BAD_REQUEST)

            uploaded_file = request.FILES['file']
            self.validate_file(uploaded_file)

            # Create document instance with validated file
            serializer = DocumentSerializer(data=request.data)
            if serializer.is_valid():
                document = serializer.save(user=request.user)

                # Set status to uploaded (parsing will be done on frontend)
                document.processing_status = 'uploaded'
                document.save()

                logger.info(f"Document uploaded successfully: {document.id} by user {request.user.id}")

                return Response({
                    'success': True,
                    'document_id': str(document.id),
                    'message': 'Document uploaded successfully. Please send parsed data to complete profile.'
                }, status=status.HTTP_200_OK)

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except ValidationError as e:
            logger.warning(f"File upload validation failed: {str(e)}")
            return Response({
                'error': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Document upload failed: {str(e)}")
            return Response({
                'error': f'Document upload failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_parsed_profile(request):
    """Update parsed profile data from frontend parsing"""
    try:
        data = request.data

        # Get the document if document_id is provided
        document = None
        if 'document_id' in data:
            try:
                document = Document.objects.get(id=data['document_id'], user=request.user)
            except Document.DoesNotExist:
                return Response({
                    'error': 'Document not found or does not belong to user'
                }, status=status.HTTP_404_NOT_FOUND)

        # Create or update parsed profile
        parsed_profile, created = ParsedProfile.objects.get_or_create(
            user=request.user,
            defaults={'document': document}
        )

        # If updating existing profile, update document reference if provided
        if not created and document:
            parsed_profile.document = document

        # Update parsed profile with data from frontend
        update_fields = [
            'first_name', 'last_name', 'email', 'phone', 'address',
            'linkedin', 'portfolio', 'summary', 'education', 'experience',
            'skills', 'certifications', 'languages', 'projects'
        ]

        for field in update_fields:
            if field in data:
                setattr(parsed_profile, field, data[field])

        # Set confidence score if provided, otherwise default
        parsed_profile.confidence_score = data.get('confidence_score', 0.90)

        # Save the profile
        parsed_profile.save()

        # Update document status to completed if document exists
        if document:
            document.processing_status = 'completed'
            document.processed_at = timezone.now()
            document.save()

        # Return the saved profile data
        serializer = ParsedProfileSerializer(parsed_profile)
        return Response({
            'success': True,
            'message': 'Profile updated successfully',
            'profile_data': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Profile update failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([ProfilePermissions])
def profile_completion_status(request):
    """Get profile completion status"""
    try:
        parsed_profile = ParsedProfile.objects.get(user=request.user)

        completion_data = {
            'completion_percentage': parsed_profile.completion_percentage,
            'missing_sections': parsed_profile.missing_sections,
            'completed_sections': parsed_profile.completed_sections
        }

        serializer = ProfileCompletionSerializer(completion_data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except ParsedProfile.DoesNotExist:
        # No profile exists yet
        return Response({
            'completion_percentage': 0,
            'missing_sections': ['personal_info', 'summary', 'education', 'experience', 'skills'],
            'completed_sections': []
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({
            'error': f'Status check failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([ProfilePermissions])
def update_user_goals(request):
    """Update user goals"""
    try:
        serializer = UserGoalUpdateSerializer(data=request.data)
        if serializer.is_valid():
            goals_data = serializer.validated_data['goals']

            with transaction.atomic():
                # Remove existing goals
                UserGoal.objects.filter(user=request.user).delete()

                # Create new goals
                new_goals = []
                for i, goal in enumerate(goals_data, 1):
                    new_goals.append(UserGoal(
                        user=request.user,
                        goal=goal,
                        priority=i
                    ))

                UserGoal.objects.bulk_create(new_goals)

            return Response({'success': True}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'error': f'Goals update failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([ProfilePermissions])
def get_user_goals(request):
    """Get user's current goals"""
    try:
        goals = UserGoal.objects.filter(user=request.user).order_by('priority')
        serializer = UserGoalSerializer(goals, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Goals retrieval failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([ProfilePermissions])
def get_parsed_profile(request):
    """Get current user's parsed profile data"""
    try:
        parsed_profile = ParsedProfile.objects.get(user=request.user)
        serializer = ParsedProfileSerializer(parsed_profile)
        return Response({
            'success': True,
            'profile_data': serializer.data
        }, status=status.HTTP_200_OK)

    except ParsedProfile.DoesNotExist:
        return Response({
            'success': False,
            'message': 'No parsed profile found. Please upload a document and send parsed data.'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'error': f'Profile retrieval failed: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([ProfilePermissions])
def get_comprehensive_user_profile(request):
    """Get comprehensive user profile data in a single request"""
    try:
        from .serializers import ComprehensiveUserProfileSerializer

        serializer = ComprehensiveUserProfileSerializer(request.user)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Failed to retrieve user profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Profile Management Endpoints for Individual Sections

@api_view(['POST'])
@permission_classes([ProfilePermissions])
def create_education_profile(request):
    """Create a new education entry"""
    try:
        serializer = EducationProfileSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'error': f'Failed to create education profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([ProfilePermissions])
def create_experience_profile(request):
    """Create a new experience entry"""
    from .serializers import ExperienceProfileSerializer
    try:
        serializer = ExperienceProfileSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'error': f'Failed to create experience profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



# @api_view(['POST'])
# @permission_classes([IsAuthenticated])
# def create_project_profile(request):
#     """Create a new project entry"""
#     try:
#         from .serializers import ProjectsProfileSerializer

#         serializer = ProjectsProfileSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response({
#                 'success': True,
#                 'data': serializer.data
#             }, status=status.HTTP_201_CREATED)

#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     except Exception as e:
#         return Response({
#             'error': f'Failed to create project profile: {str(e)}'
#         }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
@api_view(['POST'])
@permission_classes([ProfilePermissions])
def create_project_profile(request):
    """Create a new project entry"""
    try:
        serializer = ProjectsProfileSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_201_CREATED)

        # Log serializer errors for debugging
        logger.error(f"Serializer errors: {serializer.errors}")

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        logger.error(f"Failed to create project profile: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return Response({
            'error': f'Failed to create project profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([ProfilePermissions])
def project_detail_view(request, pk):
    try:
        project = ProjectsProfile.objects.get(pk=pk, user=request.user)
    except ProjectsProfile.DoesNotExist:
        return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT':
        serializer = ProjectsProfileSerializer(project, data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({'success': True, 'data': serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'DELETE':
        project.delete()
        return Response({'success': True, 'message': 'Project deleted'})

@api_view(['POST', 'GET'])
@permission_classes([ProfilePermissions])
def manage_career_profile(request):
    """Create or get career profile"""
    try:
        from .models import CareerProfile
        from .serializers import CareerProfileSerializer

        if request.method == 'GET':
            try:
                career_profile = CareerProfile.objects.get(user=request.user)
                serializer = CareerProfileSerializer(career_profile)
                return Response({
                    'success': True,
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
            except CareerProfile.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'No career profile found'
                }, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'POST':
            career_profile, created = CareerProfile.objects.get_or_create(
                user=request.user,
                defaults=request.data
            )

            if not created:
                # Update existing profile
                for field, value in request.data.items():
                    if hasattr(career_profile, field):
                        setattr(career_profile, field, value)
                career_profile.save()

            serializer = CareerProfileSerializer(career_profile)
            return Response({
                'success': True,
                'data': serializer.data,
                'created': created
            }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Failed to manage career profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST', 'GET'])
@permission_classes([ProfilePermissions])
def manage_opportunities_interest(request):
    """Create or update opportunities interest"""
    try:
        from .models import OpportunitiesInterest
        from .serializers import OpportunitiesInterestSerializer

        if request.method == 'GET':
            try:
                interest = OpportunitiesInterest.objects.get(user=request.user)
                serializer = OpportunitiesInterestSerializer(interest)
                return Response({
                    'success': True,
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
            except OpportunitiesInterest.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'No opportunities interest found'
                }, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'POST':
            interest, created = OpportunitiesInterest.objects.get_or_create(
                user=request.user,
                defaults=request.data
            )

            if not created:
                # Update existing
                for field, value in request.data.items():
                    if hasattr(interest, field):
                        setattr(interest, field, value)
                interest.save()

            serializer = OpportunitiesInterestSerializer(interest)
            return Response({
                'success': True,
                'data': serializer.data,
                'created': created
            }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Failed to manage opportunities interest: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST', 'GET'])
@permission_classes([ProfilePermissions])
def manage_recommendation_priority(request):
    """Create or update recommendation priority"""
    try:
        from .models import RecommendationPriority
        from .serializers import RecommendationPrioritySerializer

        if request.method == 'GET':
            try:
                priority = RecommendationPriority.objects.get(user=request.user)
                serializer = RecommendationPrioritySerializer(priority)
                return Response({
                    'success': True,
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
            except RecommendationPriority.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'No recommendation priority found'
                }, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'POST':
            priority, created = RecommendationPriority.objects.get_or_create(
                user=request.user,
                defaults=request.data
            )

            if not created:
                # Update existing
                for field, value in request.data.items():
                    if hasattr(priority, field):
                        setattr(priority, field, value)
                priority.save()

            serializer = RecommendationPrioritySerializer(priority)
            return Response({
                'success': True,
                'data': serializer.data,
                'created': created
            }, status=status.HTTP_200_OK if not created else status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'error': f'Failed to manage recommendation priority: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST', 'GET'])
@permission_classes([ProfilePermissions])
def manage_personal_profile(request):
    """Create or update personal profile information"""
    try:
        from .models import UserProfile
        from .serializers import UserProfileSerializer

        if request.method == 'GET':
            # Get existing profile or return empty data
            try:
                profile = UserProfile.objects.get(user=request.user)
                serializer = UserProfileSerializer(profile)
                return Response({
                    'success': True,
                    'data': serializer.data
                }, status=status.HTTP_200_OK)
            except UserProfile.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'No profile found'
                }, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'POST':
            # Create or update profile
            profile, created = UserProfile.objects.get_or_create(
                user=request.user,
                defaults={}
            )

            # Update profile fields
            update_fields = ['name', 'email', 'phone_number', 'country', 'goal']
            for field in update_fields:
                if field in request.data:
                    setattr(profile, field, request.data[field])

            # Handle CV upload if present
            if 'cv_file' in request.FILES:
                uploaded_file = request.FILES['cv_file']
                profile.cv_file = uploaded_file.read()
                profile.cv_filename = uploaded_file.name
                profile.cv_mime = uploaded_file.content_type

            # Also update user's basic info
            if 'first_name' in request.data:
                request.user.first_name = request.data['first_name']
            if 'last_name' in request.data:
                request.user.last_name = request.data['last_name']
            if 'email' in request.data:
                request.user.email = request.data['email']
            if 'country' in request.data:
                request.user.country = request.data['country']

            request.user.save()
            profile.save()

            serializer = UserProfileSerializer(profile)
            return Response({
                'success': True,
                'data': serializer.data,
                'created': created
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'error': f'Failed to manage personal profile: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
